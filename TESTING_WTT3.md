# Testing WTT3 Import Functionality

This guide shows you how to test the WTT3 (Wyse Timetables) import functionality.

## Prerequisites

1. **Run the migration** (already done):
   ```bash
   uv run manage.py migrate
   ```

2. **Configure API settings** (optional, in your `settings.py`):
   ```python
   WTT3_API_URL = "https://wtt3.docs.apiary.io"  # or your actual API URL
   WTT3_API_KEY = "your-api-key-here"  # if authentication is required
   ```

## Testing Methods

### 1. Management Command (Recommended)

#### Dry Run (Test API Connection)
Test the API connection without importing data:
```bash
uv run manage.py import_wtt3 --dry-run
```

#### Basic Import
Import all reservations:
```bash
uv run manage.py import_wtt3
```

#### Import with Custom API URL
```bash
uv run manage.py import_wtt3 --api-url "https://your-wtt3-api.com"
```

#### Import with API Key
```bash
uv run manage.py import_wtt3 --api-key "your-api-key"
```

#### Import with Date Range
```bash
uv run manage.py import_wtt3 --start-date "2025-01-01" --end-date "2025-12-31"
```

#### Full Example
```bash
uv run manage.py import_wtt3 \
  --api-url "https://wtt3.docs.apiary.io" \
  --api-key "your-key" \
  --start-date "2025-01-01T00:00:00" \
  --end-date "2025-12-31T23:59:59"
```

### 2. Django Shell

Interactive testing in Django shell:

```bash
uv run python manage.py shell
```

Then in the shell:

```python
from reservations.models import Reservation
from datetime import datetime
from django.utils import timezone

# Basic import
created, updated = Reservation.objects.import_from_wtt3()
print(f"Created: {created}, Updated: {updated}")

# Import with date range
start = datetime(2025, 1, 1, tzinfo=timezone.utc)
end = datetime(2025, 12, 31, tzinfo=timezone.utc)
created, updated = Reservation.objects.import_from_wtt3(
    start_date=start,
    end_date=end
)

# Import with custom settings
created, updated = Reservation.objects.import_from_wtt3(
    api_url="https://your-api-url.com",
    api_key="your-api-key"
)

# Check imported reservations
reservations = Reservation.objects.filter(external_id__isnull=False)
print(f"Total WTT3 reservations: {reservations.count()}")
for res in reservations[:5]:
    print(f"{res.external_id}: {res.start} - {res.end}, {res.reason}")
```

### 3. Unit Tests

Run the automated tests:

```bash
uv run python manage.py test reservations.tests.WTT3ImportTestCase
```

Or run all tests:
```bash
uv run python manage.py test
```

### 4. Python Script

Create a test script `test_import.py`:

```python
#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
django.setup()

from reservations.models import Reservation
from datetime import datetime
from django.utils import timezone

# Test import
try:
    created, updated = Reservation.objects.import_from_wtt3()
    print(f"Success! Created: {created}, Updated: {updated}")
except Exception as e:
    print(f"Error: {e}")
```

Run it:
```bash
uv run python test_import.py
```

## Verifying Results

### Check Imported Reservations

```python
from reservations.models import Reservation

# Count imported reservations
wtt3_count = Reservation.objects.filter(external_id__isnull=False).count()
print(f"Total WTT3 reservations: {wtt3_count}")

# View recent imports
recent = Reservation.objects.filter(
    external_id__isnull=False
).order_by('-id')[:10]
for res in recent:
    print(f"ID: {res.external_id}, {res.start} - {res.end}, {res.reason}")
```

### Check Logs

The import function logs to Django's logging system. Check logs for:
- API connection status
- Import progress
- Errors and warnings

## Troubleshooting

### Common Issues

1. **API Connection Error**
   - Verify the API URL is correct
   - Check network connectivity
   - Verify API key if required

2. **No Reservations Imported**
   - Check API response format matches expected structure
   - Verify date filters aren't excluding all data
   - Check logs for warnings about missing fields

3. **Import Errors**
   - Check that Reservable objects exist for any reservable slugs in API data
   - Verify User objects exist for any owner emails in API data
   - Check datetime format matches ISO 8601

### Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Mock Testing

For testing without hitting the real API, use the unit tests which mock the API responses.