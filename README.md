<div align="center">

# 🎱 Royal Snooker Academy

### Premium Snooker Academy Website & Online Table Booking Platform

<p>
  <strong>A production Django application for table reservations, academy operations, customer communication, and content management.</strong>
</p>

<p>
  <a href="https://royal-snooker-academy.onrender.com/">🌐 Live Website</a>
  &nbsp;•&nbsp;
  <a href="https://github.com/R0hittpal/Royal_Snooker_Academy">📦 GitHub Repository</a>
</p>

<br>

<img src="https://img.shields.io/badge/Django-6.1.1-0C4A3A?style=for-the-badge&logo=django&logoColor=white" alt="Django">
<img src="https://img.shields.io/badge/Python-3.14.5-0B1512?style=for-the-badge&logo=python&logoColor=E7CB70" alt="Python">
<img src="https://img.shields.io/badge/PostgreSQL-Production-D4AF37?style=for-the-badge&logo=postgresql&logoColor=07100D" alt="PostgreSQL">
<img src="https://img.shields.io/badge/Render-Deployed-06382D?style=for-the-badge&logo=render&logoColor=white" alt="Render">
<img src="https://img.shields.io/badge/Brevo-Transactional_Email-07513F?style=for-the-badge&logo=brevo&logoColor=white" alt="Brevo">

</div>

---

## ✨ At a Glance

| Area | What RSA Provides |
|---|---|
| 🎱 **Customer Booking** | Date, time, table, duration, customer details and confirmation |
| 🟢 **Availability** | Live table availability and booking-overlap protection |
| 📧 **Email** | Transactional booking and completion emails through Brevo |
| 🧑‍💼 **Manager Operations** | Dedicated RSA Manager Login and Operations Center |
| 🔐 **Owner Administration** | Django Admin + Jazzmin |
| 📱 **Responsive UX** | Premium desktop and mobile experience |
| 🖼️ **Academy Content** | Gallery, coaching, membership, tournaments and contact |
| ☁️ **Production** | Render + PostgreSQL + Gunicorn + WhiteNoise |

---

## 🎯 Project Overview

**Royal Snooker Academy (RSA)** is a Django-based website and online snooker table slot-booking system built for a real academy environment.

The platform combines the public customer experience with operational tools for academy staff.

```text
                         ROYAL SNOOKER ACADEMY
                                  │
                 ┌────────────────┴────────────────┐
                 │                                 │
              CUSTOMER                            STAFF
                 │                                 │
                 ▼                                 ▼
         Public RSA Website                Authentication Layer
                 │                                 │
       ┌─────────┼─────────┐               ┌───────┴────────┐
       │         │         │               │                │
    Booking   Content   Contact        Manager            Owner
       │                              Login               Login
       ▼                                 │                  │
 Django Booking Engine                  ▼                  ▼
       │                          Operations Center   Django Admin
       │
       ├── Availability
       ├── Validation
       ├── Booking Lifecycle
       └── Email Notifications
                         │
                         ▼
                  Brevo Transactional API
                         │
                         ▼
                    Customer Inbox
```

---

## 🚀 Core Features

### 🎱 Online Table Booking

Customers follow a clear five-step journey:

```text
01 Date  →  02 Time  →  03 Table  →  04 Details  →  05 Confirm
```

The booking system handles:

- Booking date
- Start time
- Session duration
- Table selection
- Customer name
- Phone number
- Email address
- Amount
- Booking reference
- Booking status
- Table availability
- Academy operating hours

### 📅 Booking Integrity

Server-side booking validation protects the reservation workflow:

- Prevents overlapping bookings
- Checks table availability
- Validates academy operating hours
- Validates customer information
- Calculates session duration and amount
- Generates booking references
- Supports cancellation
- Prevents premature completion
- Uses POST → Redirect → GET where appropriate

A booking can only be completed after its scheduled session has ended.

---

## 🧑‍💼 RSA Operations Center

The project includes a dedicated interface for academy managers.

```text
RSA Manager Login
       │
       ▼
RSA Operations Center
       │
       ├── Today's KPIs
       ├── Today's Revenue
       ├── Today's Schedule
       ├── Live Table Floor
       ├── Upcoming Reservations
       ├── Booking Management
       ├── Search & Filters
       ├── Date Filtering
       ├── Pagination
       ├── Cancel Booking
       └── Complete Booking
```

The manager does **not** need Django Admin credentials for normal daily operations.

The Operations Center includes completion protection and a current-session / **NOW** indicator for active sessions.

---

## 🔐 Owner Administration

Owner-level administration remains separate from daily manager operations.

```text
Owner
  │
  ▼
Django Admin / Jazzmin
  │
  ├── Tables
  ├── Bookings
  ├── Academy Settings
  ├── Site Settings
  ├── Home Page Settings
  ├── Coaching
  ├── Membership
  ├── Tournaments
  ├── Gallery
  ├── Users
  └── Groups
```

This separation keeps operational tasks and system administration distinct.

---

## 📧 Transactional Email

Production email delivery uses the **Brevo Transactional Email API** over HTTPS.

```text
Customer confirms booking
          │
          ▼
   Django booking logic
          │
          ▼
      PostgreSQL
          │
          ▼
    RSA email builder
          │
          ▼
      Brevo API
          │
          ▼
    Customer inbox
```

Supported transactional emails:

- Booking confirmation
- Booking completion / thank-you

The email design includes:

- RSA branding
- Royal Snooker Academy logo
- Booking reference
- Customer information
- Session details
- Table information
- Duration
- Amount
- Booking status

### Production Email Configuration

```env
RSA_EMAIL_PROVIDER=brevo
RSA_BREVO_API_KEY=<secret>
RSA_BREVO_SENDER_EMAIL=<verified sender>
RSA_BREVO_SENDER_NAME=Royal Snooker Academy
RSA_EMAIL_LOGO_URL=https://your-public-domain/static/images/royal_snooker_favicon_under_50kb.png
```

`RSA_EMAIL_LOGO_URL` must be publicly reachable so Brevo can display the same RSA favicon crest used by the website.

> **Security:** Never commit API keys, SMTP passwords, database URLs, Django secrets, or `.env` files to GitHub.

---

## 🌐 Public Website

The customer-facing website includes:

| Page | Purpose |
|---|---|
| 🏠 **Home** | Academy introduction, highlights and primary booking CTAs |
| 🎱 **Tables & Slots** | Table information and availability |
| 📅 **Booking** | Complete reservation workflow |
| 🏆 **Coaching** | Coaching programs and pricing |
| 💳 **Membership** | Membership plans |
| 🏅 **Tournaments** | Tournament information |
| 🖼️ **Gallery** | Academy gallery with fullscreen lightbox |
| 📞 **Contact** | Contact and communication options |

The public website uses a consistent premium RSA visual identity across all major pages.

---

## 🎨 Design System

The project follows a premium, modern snooker-club aesthetic.

### Brand Palette

| Color | Hex |
|---|---|
| Deep Black | `#07100D` |
| Emerald | `#06382D` |
| Green | `#07513F` |
| Gold | `#D4AF37` |
| Light Gold | `#E7CB70` |
| Ivory | `#F7F5EF` |
| Dark Text | `#18322B` |
| Muted Text | `#66746F` |

### Design Direction

- Premium
- Modern
- Elegant
- Sporty
- Professional
- High-end snooker club
- Strong call-to-action hierarchy
- Responsive mobile experience
- Consistent RSA branding

**Typography:** Inter + Playfair Display

---

## ♿ UX & Accessibility

The application includes:

- Responsive desktop and mobile layouts
- Visible keyboard focus states
- Reduced-motion support
- Clear available / selected / booked states
- Strong CTA hierarchy
- Mobile navigation
- Accessible contact-action labels
- Gallery lightbox keyboard navigation
- Escape-key support for overlays
- Scroll-lock behavior for modal interfaces

---

## 🛠️ Technology Stack

### Backend

- Python 3.14.5
- Django 6.1.1
- Django Authentication
- Django Sessions
- Django Admin
- django-jazzmin

### Database

**Development**

- SQLite

**Production**

- PostgreSQL
- `dj-database-url`
- `psycopg2-binary`

### Frontend

- Django Templates
- HTML
- CSS
- JavaScript
- Responsive UI
- Utility-class-based styling in the existing templates

### Email

- Brevo Transactional Email API
- Python `requests`

### Deployment

- Render Web Service
- Gunicorn
- WhiteNoise
- PostgreSQL

---

## 📁 Project Structure

```text
Royal_Snooker_Academy/
│
├── config/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── core/
│   ├── views.py
│   ├── urls.py
│   └── ...
│
├── bookings/
│   ├── models.py
│   ├── admin.py
│   └── ...
│
├── templates/
│   ├── home.html
│   ├── booking.html
│   ├── tables.html
│   ├── coaching.html
│   ├── membership.html
│   ├── tournaments.html
│   ├── gallery.html
│   ├── contact.html
│   ├── manager_login.html
│   ├── admin_dashboard.html
│   └── ...
│
├── static/
│   └── images/
│       ├── RSA_logo.png
│       ├── Royal_Snooker_Academy_Email_Logo.jpg
│       └── RSA_Banner.png
│
├── build.sh
├── manage.py
├── requirements.txt
├── .python-version
├── .env.example
└── README.md
```

---

## 💻 Local Development

### 1. Clone the repository

```bash
git clone https://github.com/R0hittpal/Royal_Snooker_Academy.git
cd Royal_Snooker_Academy
```

### 2. Create a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
```

Activate:

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file:

```env
DJANGO_SECRET_KEY=change-this-for-local-development
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

RSA_EMAIL_PROVIDER=smtp

RSA_EMAIL_HOST_USER=
RSA_EMAIL_HOST_PASSWORD=
RSA_DEFAULT_FROM_EMAIL=
```

For local Brevo testing, configure the Brevo variables instead.

**Never commit `.env` or production credentials.**

### 5. Apply migrations

```powershell
python manage.py migrate
```

### 6. Create an owner/admin user

```powershell
python manage.py createsuperuser
```

### 7. Start Django

```powershell
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

---

## ☁️ Production Deployment

The application is deployed using **Render**.

### Build Command

```bash
bash build.sh
```

The build process:

```text
Install requirements
       ↓
collectstatic
       ↓
migrate
```

### Start Command

```bash
gunicorn config.wsgi:application
```

### Database Behavior

```text
Local Development
       │
       ▼
     SQLite

Production
       │
       ▼
   DATABASE_URL
       │
       ▼
   PostgreSQL
```

### Production Security

With `DEBUG=False`, the application enables:

- HTTPS redirect
- Secure session cookies
- Secure CSRF cookies
- HSTS
- Content-type sniffing protection
- Referrer policy
- Clickjacking protection
- Render proxy HTTPS handling

Production settings fail at startup when required configuration is missing.
Configure all of the following in Render Environment Variables:

- `DJANGO_SECRET_KEY`: a long, randomly generated production secret
- `DATABASE_URL`: the Render PostgreSQL connection URL
- `DJANGO_ALLOWED_HOSTS`: the production domain(s), unless Render supplies
  `RENDER_EXTERNAL_HOSTNAME`
- `DJANGO_DEBUG=False`: set explicitly for production

When `DJANGO_DEBUG` is omitted, it defaults to `False`. Local development
should explicitly set `DJANGO_DEBUG=True` in `.env`; SQLite remains the local
database default. Invalid boolean values, missing production hosts/secrets, or
a non-PostgreSQL production database URL stop startup with a configuration
error.

---

## 🔑 Environment Variables

The application uses environment-based configuration for secrets and deployment-specific settings.

```text
DJANGO_SECRET_KEY
DJANGO_DEBUG
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
DATABASE_URL
RENDER_EXTERNAL_HOSTNAME

RSA_EMAIL_PROVIDER
RSA_BREVO_API_KEY
RSA_BREVO_SENDER_EMAIL
RSA_BREVO_SENDER_NAME
RSA_EMAIL_LOGO_URL

RSA_EMAIL_HOST_USER
RSA_EMAIL_HOST_PASSWORD
RSA_DEFAULT_FROM_EMAIL
```

### Never Commit

```text
.env
API keys
SMTP passwords
Django SECRET_KEY
DATABASE_URL
Other credentials
```

Production secrets should be configured through Render Environment Variables.

---

## 📦 Static Files

Production static assets use:

```text
Django collectstatic
        ↓
staticfiles/
        ↓
WhiteNoise
        ↓
Render Web Service
```

WhiteNoise provides production static-file serving without requiring a separate static-file server.

---

## 📝 Content Management

Database-backed academy content can be updated through Django Admin.

Examples include:

- Academy settings
- Site settings
- Home page settings
- Tables
- Coaching
- Membership
- Tournaments
- Gallery/content
- Bookings
- Users and groups

Database content changes do **not** require a GitHub deployment.

Code and functionality changes follow the Git → GitHub → Render deployment workflow.

---

## 🔄 Git Workflow

The project uses feature branches for development.

### Start a feature

```bash
git checkout main
git pull origin main

git checkout -b feature-name
```

### Test and commit

```bash
git status
git diff --check
git add .
git commit -m "Describe the change"
git push origin feature-name
```

### Deployment flow

```text
Feature Branch
      │
      ▼
Pull Request
      │
      ▼
main
      │
      ▼
Render Deployment
      │
      ▼
Production
```

The `main` branch represents the production codebase.

---

## 📊 Current Production Status

| Component | Status |
|---|:---:|
| Public RSA Website | ✅ |
| Responsive Navigation | ✅ |
| Tables & Slots | ✅ |
| Online Booking | ✅ |
| Availability Checking | ✅ |
| Booking Validation | ✅ |
| Booking Confirmation | ✅ |
| Booking Cancellation | ✅ |
| Booking Completion | ✅ |
| Confirmation Emails | ✅ |
| Completion Emails | ✅ |
| Brevo Production Delivery | ✅ |
| Gallery + Lightbox | ✅ |
| Coaching | ✅ |
| Membership | ✅ |
| Tournaments | ✅ |
| Contact | ✅ |
| Django Admin / Jazzmin | ✅ |
| RSA Manager Login | ✅ |
| RSA Operations Center | ✅ |
| PostgreSQL Production Database | ✅ |
| Render Deployment | ✅ |
| WhiteNoise Static Files | ✅ |
| Git/GitHub Workflow | ✅ |

---

## 🗺️ Roadmap

Potential future enhancements:

- [ ] Custom RSA email domain
- [ ] SPF / DKIM / DMARC authentication
- [ ] Persistent production media storage
- [ ] Online payment integration
- [ ] Customer booking history
- [ ] Automated booking reminders
- [ ] Membership management
- [ ] Advanced reporting
- [ ] Revenue analytics
- [ ] Additional customer notification channels
- [ ] Granular manager permissions
- [ ] Production monitoring and error tracking

These should be implemented incrementally without disrupting the existing booking and operations workflow.

---

## 🧭 Development Principles

When extending the project:

1. **Preserve working functionality.**
2. **Inspect the current implementation before modifying it.**
3. **Avoid unnecessary rewrites.**
4. **Keep Owner and Manager permissions separated.**
5. **Do not change database models unless genuinely required.**
6. **Never commit secrets.**
7. **Test locally before production deployment.**
8. **Use feature branches for significant changes.**
9. **Keep the RSA visual identity consistent.**
10. **Make incremental changes and test each meaningful change.**
11. **Treat the application as a real production business system.**

---

## 🌐 Project Links

| Resource | Link |
|---|---|
| 🌐 **Live Website** | https://royal-snooker-academy.onrender.com/ |
| 📦 **GitHub Repository** | https://github.com/R0hittpal/Royal_Snooker_Academy |

---

<div align="center">

### 🎱 Royal Snooker Academy

**PLAY. PRACTICE. PERFORM.**

Built with Django · Designed for RSA · Deployed for production

</div>
