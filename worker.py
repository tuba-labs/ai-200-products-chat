"""One question at a time per pod, with explicit acknowledgements and lock renewal."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import timedelta
import json
import logging
import signal
import threading

from azure.servicebus import ServiceBusClient, ServiceBusMessage, AutoLockRenewer
from rag_core.chat import validate_request, process_question, reply, cache_reply, InvalidRequest
from rag_core.config import load_settings
from rag_core.models import AzureModels

LOG = logging.getLogger('products-chat')
STOP = threading.Event()


class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == '/health' else 404)
        self.end_headers()
        self.wfile.write(b'worker ready')

    def log_message(self, *_):
        pass


def publish(sender, payload):
    sender.send_messages(ServiceBusMessage(json.dumps(payload), message_id=payload['requestId'],
                         correlation_id=payload['correlationId'], content_type='application/json', time_to_live=timedelta(minutes=8)))


def main():
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(levelname)s %(message)s')
    LOG.setLevel(logging.INFO)
    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda *_: STOP.set())
    settings = load_settings()
    model = AzureModels(settings)
    count = settings.integer('retrieval-count', 1, 8)
    similarity = float(settings.values['min-similarity'])
    with settings.connect() as connection:
        connection.execute('SELECT 1 FROM chat_requests LIMIT 1')
    health = ThreadingHTTPServer(('0.0.0.0', 8080), Health)
    threading.Thread(target=health.serve_forever, daemon=True).start()
    LOG.info('Worker ready: retrieval_count=%s concurrency=1 prefetch=0', count)
    with ServiceBusClient(settings.values['servicebus-host'], settings.credential()) as bus, AutoLockRenewer() as renewer:
        with bus.get_queue_receiver('chat-requests', prefetch_count=0, max_wait_time=5) as receiver, \
             bus.get_queue_sender('chat-replies') as sender:
            while not STOP.is_set():
                for message in receiver.receive_messages(max_message_count=1, max_wait_time=5):
                    renewer.register(receiver, message, max_lock_renewal_duration=600)
                    try:
                        request = validate_request(json.loads(str(message)), message.message_id, message.correlation_id)
                    except (ValueError, TypeError, KeyError):
                        receiver.dead_letter_message(message, reason='invalid_request', error_description='Body or correlation headers are invalid')
                        continue
                    try:
                        with settings.connect() as connection:
                            result = process_question(connection, request, model, count, similarity)
                        publish(sender, result)
                        receiver.complete_message(message)
                        LOG.info('request=%s correlation=%s status=%s sources=%s', request['requestId'],
                                 request['correlationId'], result['status'], len(result['sources']))
                    except InvalidRequest:
                        receiver.dead_letter_message(message, reason='persistent_request_mismatch',
                                                     error_description='Message does not match an existing persistent request')
                    except Exception as error:
                        LOG.warning('request=%s failure_type=%s delivery=%s', request['requestId'],
                                    type(error).__name__, message.delivery_count)
                        if message.delivery_count >= 4:
                            result = reply(request, 'failed', error='worker_failed_after_retries')
                            with settings.connect() as connection:
                                cache_reply(connection, result)
                            publish(sender, result)
                            receiver.dead_letter_message(message, reason='processing_failed',
                                                         error_description='See worker logs by request ID; inspect model quota and database connectivity')
                        else:
                            # Bounded backoff, while the message lock is still
                            # renewed, avoids immediately exhausting deliveries
                            # during a transient throttle or connection fault.
                            STOP.wait(min(60, 5 * 2 ** max(1, message.delivery_count)))
                            receiver.abandon_message(message)
    health.shutdown()


if __name__ == '__main__':
    main()
