from django.core.management.base import BaseCommand
from datetime import date
from attendance.models import Holiday


# --- Turkish public holidays data ---

STATIC_HOLIDAYS = {
    'New Year\'s Day': (1, 1),
    'National Sovereignty and Children\'s Day': (4, 23),
    'Labor and Solidarity Day': (5, 1),
    'Commemoration of Atatürk, Youth and Sports Day': (5, 19),
    'Democracy and National Unity Day': (7, 15),
    'Victory Day': (8, 30),
    'Republic Day': (10, 29),
}

RELIGIOUS_HOLIDAYS = {
    2024: [
        (4, 10, 'Ramadan Feast Day 1'),
        (4, 11, 'Ramadan Feast Day 2'),
        (4, 12, 'Ramadan Feast Day 3'),
        (6, 15, 'Sacrifice Feast Day 1'),
        (6, 16, 'Sacrifice Feast Day 2'),
        (6, 17, 'Sacrifice Feast Day 3'),
        (6, 18, 'Sacrifice Feast Day 4'),
    ],
    2025: [
        (3, 30, 'Ramadan Feast Day 1'),
        (3, 31, 'Ramadan Feast Day 2'),
        (4, 1, 'Ramadan Feast Day 3'),
        (6, 5, 'Sacrifice Feast Day 1'),
        (6, 6, 'Sacrifice Feast Day 2'),
        (6, 7, 'Sacrifice Feast Day 3'),
        (6, 8, 'Sacrifice Feast Day 4'),
    ],
    2026: [
        (3, 20, 'Ramadan Feast Day 1'),
        (3, 21, 'Ramadan Feast Day 2'),
        (3, 22, 'Ramadan Feast Day 3'),
        (5, 26, 'Sacrifice Feast Day 1'),
        (5, 27, 'Sacrifice Feast Day 2'),
        (5, 28, 'Sacrifice Feast Day 3'),
        (5, 29, 'Sacrifice Feast Day 4'),
    ],
    2027: [
        (3, 9, 'Ramadan Feast Day 1'),
        (3, 10, 'Ramadan Feast Day 2'),
        (3, 11, 'Ramadan Feast Day 3'),
        (5, 15, 'Sacrifice Feast Day 1'),
        (5, 16, 'Sacrifice Feast Day 2'),
        (5, 17, 'Sacrifice Feast Day 3'),
        (5, 18, 'Sacrifice Feast Day 4'),
    ],
    2028: [
        (2, 26, 'Ramadan Feast Day 1'),
        (2, 27, 'Ramadan Feast Day 2'),
        (2, 28, 'Ramadan Feast Day 3'),
        (5, 3, 'Sacrifice Feast Day 1'),
        (5, 4, 'Sacrifice Feast Day 2'),
        (5, 5, 'Sacrifice Feast Day 3'),
        (5, 6, 'Sacrifice Feast Day 4'),
    ],
    2029: [
        (2, 14, 'Ramadan Feast Day 1'),
        (2, 15, 'Ramadan Feast Day 2'),
        (2, 16, 'Ramadan Feast Day 3'),
        (4, 22, 'Sacrifice Feast Day 1'),
        (4, 23, 'Sacrifice Feast Day 2'),
        (4, 24, 'Sacrifice Feast Day 3'),
        (4, 25, 'Sacrifice Feast Day 4'),
    ],
    2030: [
        (2, 3, 'Ramadan Feast Day 1'),
        (2, 4, 'Ramadan Feast Day 2'),
        (2, 5, 'Ramadan Feast Day 3'),
        (4, 11, 'Sacrifice Feast Day 1'),
        (4, 12, 'Sacrifice Feast Day 2'),
        (4, 13, 'Sacrifice Feast Day 3'),
        (4, 14, 'Sacrifice Feast Day 4'),
    ],
}

HOLIDAY_DESCRIPTIONS = {
    'New Year\'s Day': 'January 1 - New Year\'s Day',
    'National Sovereignty and Children\'s Day': 'April 23 - National Sovereignty and Children\'s Day',
    'Labor and Solidarity Day': 'May 1 - Labor and Solidarity Day',
    'Commemoration of Atatürk, Youth and Sports Day': 'May 19 - Commemoration of Atatürk, Youth and Sports Day',
    'Democracy and National Unity Day': 'July 15 - Democracy and National Unity Day',
    'Victory Day': 'August 30 - Victory Day',
    'Republic Day': 'October 29 - Republic Day',
    'Ramadan Feast': 'Religious holiday (Eid al-Fitr / Şeker Bayramı)',
    'Sacrifice Feast': 'Religious holiday (Eid al-Adha / Kurban Bayramı)',
}


class Command(BaseCommand):
    # Management command: populate the database with Turkish public holidays
    help = 'Seeds Turkish public holidays into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--years',
            nargs='+',
            type=int,
            default=list(range(2024, 2031)),
            help='Years to seed holidays for (default: 2024-2030)',
        )

    def handle(self, *args, **options):
        years = options['years']
        created_count = 0
        updated_count = 0

        # Seed fixed-date national holidays
        for year in years:
            for holiday_name, (month, day) in STATIC_HOLIDAYS.items():
                holiday_date = date(year, month, day)
                obj, created = Holiday.objects.update_or_create(
                    date=holiday_date,
                    year=year,
                    defaults={
                        'name': holiday_name,
                        'description': HOLIDAY_DESCRIPTIONS.get(holiday_name, ''),
                        'is_active': True,
                    },
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        # Seed variable-date religious holidays
        for year, entries in RELIGIOUS_HOLIDAYS.items():
            if year not in years:
                continue
            for month, day, name in entries:
                holiday_date = date(year, month, day)
                base_name = 'Ramadan Feast' if 'Ramadan' in name else 'Sacrifice Feast'
                obj, created = Holiday.objects.update_or_create(
                    date=holiday_date,
                    year=year,
                    defaults={
                        'name': name,
                        'description': HOLIDAY_DESCRIPTIONS.get(base_name, ''),
                        'is_active': True,
                    },
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done. Created {created_count} new holidays, updated {updated_count} existing.'
        ))
