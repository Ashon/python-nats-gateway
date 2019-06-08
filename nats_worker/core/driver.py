import logging
import time

from nats.aio.client import Client

from nats_worker.core.utils import InterruptBumper


class NatsDriver(object):
    nats = None

    def __init__(self, urls):
        self.urls = urls

    async def get_connection(self, loop):
        self.nats = Client()

        await self.nats.connect(
            servers=self.urls,
            loop=loop,
            error_cb=self.on_error,
            disconnected_cb=self.on_disconnected,
            closed_cb=self.on_closed,
            reconnected_cb=self.on_reconnected
        )

        return self.nats

    @staticmethod
    async def on_error(exception):
        logging.error(f'{exception}')

    @staticmethod
    async def on_disconnected():
        logging.info(f'disconnected')

    @staticmethod
    async def on_closed():
        logging.info(f'closed')

    @staticmethod
    async def on_reconnected():
        logging.info(f'reconnected')

    def create_task(self, task_fn):
        logging.debug(f'Create task [task_fn={task_fn.__name__}]')

        async def run_task(msg):
            if self.nats.is_draining:
                logging.debug('Connection is draining')
                raise Exception('draining')

            logging.info((
                'Received message. '
                f'[subject={msg.subject}][fn={task_fn.__name__}]'
                f'[from={msg.reply}]'
            ))

            try:
                with InterruptBumper(attempts=3):
                    now = time.perf_counter()
                    data = msg.data.decode()
                    ret = task_fn(data)
                    elapsed = (time.perf_counter() - now) * 1000

                    if msg.reply:
                        await self.nats.publish(msg.reply, ret.encode())

                    logging.info((
                        'Task finished. '
                        f'[subject={msg.subject}][fn={task_fn.__name__}]'
                        f'[elapsed={elapsed:.3f}ms]'
                    ))

            except KeyboardInterrupt:
                await self.nats.publish(
                    msg.reply, 'KeyboardInterrupt'.encode())
                raise

        return run_task

    async def close(self):
        logging.debug('Drain subscriptions')

        await self.nats.flush()
        await self.nats.drain()
        await self.nats.close()