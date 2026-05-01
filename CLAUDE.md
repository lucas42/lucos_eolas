# lucos_eolas

## Migrations and Translations

When you change models in `lucos_eolas`, you **MUST NOT** run `makemigrations` directly. Instead:

1. **Modify Models**: Make your changes to `models.py`.
2. **Run the update script** from the project root:
   ```bash
   ./update.sh
   ```
   This script runs migrations and updates translation files inside Docker, then syncs them back to your local filesystem.
3. **Update Translations**: After running the script, check `app/lucos_eolas/locale/ga/LC_MESSAGES/django.po` and add any missing Irish translations.
4. **Never create migrations manually**: Do not run `python manage.py makemigrations` on the host or inside the container without using the script — it ensures proper sync and environment consistency.
