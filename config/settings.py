import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured


# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


# ============================================================
# SECURITY
# ============================================================

# Keep secrets outside source control. In production, set these
# values in the environment/.env supplied by the hosting platform.
debug_value = os.getenv("DJANGO_DEBUG")

if debug_value is None:
    DEBUG = False
elif debug_value.strip().lower() in ("1", "true", "yes", "on"):
    DEBUG = True
elif debug_value.strip().lower() in ("0", "false", "no", "off"):
    DEBUG = False
else:
    raise ImproperlyConfigured(
        "DJANGO_DEBUG must be set to a recognized true or false value."
    )

DEVELOPMENT_SECRET_KEY = "django-insecure-royal-snooker-academy-dev-key-change-me"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "").strip()

if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = DEVELOPMENT_SECRET_KEY
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be configured when DEBUG is False."
        )
elif not DEBUG and SECRET_KEY == DEVELOPMENT_SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must not use the built-in development key in production."
    )

default_allowed_hosts = "127.0.0.1,localhost" if DEBUG else ""

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        default_allowed_hosts,
    ).split(",")
    if host.strip()
]

# Render provides the public hostname through RENDER_EXTERNAL_HOSTNAME.
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()

if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Production-only browser security. These remain disabled while
# DEBUG=True so the local development server continues to work.
if not DEBUG:
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "Set DJANGO_ALLOWED_HOSTS or configure RENDER_EXTERNAL_HOSTNAME "
            "when DEBUG is False."
        )
    if "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS must list specific production hosts."
        )

    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    X_FRAME_OPTIONS = "DENY"

    # Render terminates HTTPS before forwarding the request to Django.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")


# Render's hostname can be supplied automatically, while additional
# trusted origins can be provided through DJANGO_CSRF_TRUSTED_ORIGINS.
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "",
    ).split(",")
    if origin.strip()
]

if RENDER_EXTERNAL_HOSTNAME:
    render_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)


# ============================================================
# APPLICATIONS
# ============================================================

INSTALLED_APPS = [
    "jazzmin",

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "core",
    "bookings",
]


# ============================================================
# MIDDLEWARE
# ============================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ============================================================
# URL CONFIGURATION
# ============================================================

ROOT_URLCONF = "config.urls"


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",

        "DIRS": [
            BASE_DIR / "templates",
        ],

        "APP_DIRS": True,

        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",

                "core.context_processors.site_settings",
                "core.context_processors.owner_admin_dashboard",
            ],
        },
    },
]


# ============================================================
# WSGI
# ============================================================

WSGI_APPLICATION = "config.wsgi.application"


# ============================================================
# DATABASE
# ============================================================

# Local development continues to use SQLite.
# Production uses PostgreSQL through DATABASE_URL.
DATABASE_URL = os.getenv("DATABASE_URL")

if not DEBUG and not DATABASE_URL:
    raise ImproperlyConfigured(
        "DATABASE_URL must point to the production PostgreSQL database "
        "when DEBUG is False."
    )

if DATABASE_URL:
    database_config = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=not DEBUG,
    )

    if not DEBUG and database_config["ENGINE"] != "django.db.backends.postgresql":
        raise ImproperlyConfigured(
            "Production DATABASE_URL must configure PostgreSQL."
        )

    DATABASES = {
        "default": database_config,
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ============================================================
# PASSWORD VALIDATION
# ============================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ============================================================
# INTERNATIONALIZATION
# ============================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# ============================================================
# STATIC FILES
# ============================================================

STATIC_URL = "static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# collectstatic writes production static files here.
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise serves compressed, hashed static files in production.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}


# ============================================================
# MEDIA FILES
# ============================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# ============================================================
# DEFAULT PRIMARY KEY
# ============================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ============================================================
# EMAIL CONFIGURATION
# ============================================================

# Delivery provider used by send_rsa_html_email().
# Keep "smtp" for local development; use "brevo" on Render.
RSA_EMAIL_PROVIDER = os.getenv(
    "RSA_EMAIL_PROVIDER",
    "smtp",
).strip().lower()

# Brevo transactional email API settings.
RSA_BREVO_API_KEY = os.getenv(
    "RSA_BREVO_API_KEY",
    "",
)

RSA_BREVO_SENDER_EMAIL = os.getenv(
    "RSA_BREVO_SENDER_EMAIL",
    "",
)

RSA_BREVO_SENDER_NAME = os.getenv(
    "RSA_BREVO_SENDER_NAME",
    "Royal Snooker Academy",
)

# Public URL of the RSA email logo used by Brevo.
RSA_EMAIL_LOGO_URL = os.getenv(
    "RSA_EMAIL_LOGO_URL",
    "",
)

# Existing SMTP settings retained for local development.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_HOST = "smtp.gmail.com"

EMAIL_PORT = 587

EMAIL_USE_TLS = True

EMAIL_TIMEOUT = 20

EMAIL_HOST_USER = os.getenv(
    "RSA_EMAIL_HOST_USER",
    "",
)

EMAIL_HOST_PASSWORD = os.getenv(
    "RSA_EMAIL_HOST_PASSWORD",
    "",
)

DEFAULT_FROM_EMAIL = os.getenv(
    "RSA_DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER,
)


# ============================================================
# JAZZMIN ADMIN
# ============================================================

JAZZMIN_SETTINGS = {
    "site_title": "Royal Snooker Academy Admin",
    "site_header": "Royal Snooker Academy",
    "site_brand": "Royal Snooker Academy",

    "site_logo": None,
    "login_logo": None,

    "welcome_sign": "Welcome to Royal Snooker Academy Admin Portal",

    "copyright": "Royal Snooker Academy",

    "search_model": [
        "bookings.Booking",
        "bookings.Table",
    ],

    "user_avatar": None,

    "show_sidebar": True,
    "navigation_expanded": False,

    "hide_apps": [],
    "hide_models": [],

    "order_with_respect_to": [
        "bookings",
        "bookings.booking",
        "bookings.table",
        "bookings.bookingemailnotification",
        "bookings.site_settings",
        "bookings.homepagesettings",
        "auth",
        "auth.user",
        "auth.group",
    ],

    "icons": {
        "bookings": "fas fa-calendar-check",
        "bookings.Table": "fas fa-table",
        "bookings.Booking": "fas fa-calendar-alt",
        "bookings.BookingEmailNotification": "fas fa-envelope",
        "bookings.SiteSettings": "fas fa-address-card",
        "bookings.HomePageSettings": "fas fa-home",

        "auth": "fas fa-users-cog",
        "auth.User": "fas fa-user",
        "auth.Group": "fas fa-users",

        "sites": "fas fa-globe",
    },

    "custom_css": "css/admin_owner.css",
    "custom_js": None,

    "show_ui_builder": False,
}


# ============================================================
# JAZZMIN UI CUSTOMIZATION
# ============================================================

JAZZMIN_UI_TWEAKS = {
    "theme": "flatly",
    "default_theme_mode": "light",

    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,

    "brand_small_text": False,
    "brand_colour": "navbar-primary",

    "accent": "accent-primary",

    "navbar": "navbar-primary navbar-dark",
    "no_navbar_border": False,

    "sidebar": "sidebar-dark-primary",
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,

    "footer_fixed": False,

    "actions_sticky_top": False,
}
