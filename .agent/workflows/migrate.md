---
description: How to generate migrations and update translations for LucOS Eolas
---

# Migrations and Translations Workflow

When you change models in `lucos_eolas`, you MUST NOT run `makemigrations` directly. Instead, follow these steps:

1.  **Modify Models**: Make your changes to `models.py`.
2.  **Run Update Script**: Run the following command from the project root:
    ```bash
    ./update.sh
    ```
    This script handles running migrations and updating translation files within the Docker environment and syncing them back to your local filesystem.
3.  **Update Translations**: After running the script, check `app/lucos_eolas/locale/ga/LC_MESSAGES/django.po` and add any missing Irish translations.
4.  **Do Not Create Migrations Manually**: Never run `python manage.py makemigrations` manually on the host or inside the container without using the script, as it ensures proper sync and environment consistency.
