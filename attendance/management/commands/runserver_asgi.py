from django.core.management.base import BaseCommand
from daphne.cli import CommandLineInterface


class Command(BaseCommand):
    # Management command: run Daphne ASGI server for WebSocket support
    help = 'Run the ASGI server (Daphne) with WebSocket support. Use this instead of runserver for real-time features.'

    def add_arguments(self, parser):
        parser.add_argument('addrport', nargs='?', default='8000',
                            help='Optional port number, or ipaddr:port')

    def handle(self, *args, **options):
        addrport = options['addrport']
        if ':' in addrport:
            bind, port = addrport.split(':', 1)
        else:
            bind, port = '127.0.0.1', addrport
        self.stdout.write(self.style.SUCCESS(f'Starting ASGI server at http://{bind}:{port}'))
        self.stdout.write(self.style.WARNING('WebSocket support enabled.'))
        CommandLineInterface().run([
            '-b', bind,
            '-p', port,
            'timetracker.asgi:application',
        ])
