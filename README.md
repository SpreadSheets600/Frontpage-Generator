# Frontpage Generator

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Cloudflare-Workers-orange?style=for-the-badge&logo=cloudflare&logoColor=white" alt="Cloudflare Workers">
  <img src="https://img.shields.io/badge/Cloudflare-D1-orange?style=for-the-badge&logo=cloudflare&logoColor=white" alt="Cloudflare D1">
  <img src="https://img.shields.io/badge/Cloudflare-Pages-blue?style=for-the-badge&logo=cloudflare&logoColor=white" alt="Cloudflare Pages">
</p>

> A serverless web application for generating academic frontpage covers automatically. Built on Cloudflare Workers, D1, and Pages.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Local Development](#local-development)
- [API Reference](#api-reference)
- [Deployment](#deployment)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

Frontpage Generator is a serverless application that creates professional academic frontpage covers for students. It runs entirely on Cloudflare's platform:

- **Cloudflare Workers** - Serves the API backend
- **Cloudflare D1** - SQLite database for catalog and logs
- **Cloudflare Pages** - Hosts the static frontend

---

## Features

- **Automatic Frontpage Generation** - Create academic cover pages with student details (name, roll number, registration, subject, stream, semester)
- **Live Statistics** - Real-time counter showing total documents generated
- **D1-Powered Backend** - All catalog and logging data persisted in Cloudflare D1
- **Client-Side Rendering** - PNG/PDF generation happens in the browser
- **Responsive Design** - Works on mobile and desktop

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python, Cloudflare Workers |
| Database | Cloudflare D1 (SQLite) |
| Frontend | HTML, CSS, JavaScript |
| Hosting | Cloudflare Pages |

---

## Project Structure

```
Frontpage-Generator/
├── cloudflare-api/           # Cloudflare Worker
│   ├── src/
│   │   └── worker.py        # Python Worker API
│   ├── schema.sql           # D1 database schema
│   ├── wrangler.toml        # Worker configuration
│   └── .dev.vars.example    # Local development variables
│
├── static/                  # Static assets
│   ├── template.png        # Frontpage template
│   └── Sans.ttf            # Custom font
│
├── public/                  # Public static files
│
├── index.html              # Static frontend (Cloudflare Pages)
├── main.py                 # Legacy Flask entry (not needed)
├── requirements.txt        # Python dependencies
├── package.json            # NPM scripts
└── pyproject.toml          # Python project config
```

---

## Getting Started

### Prerequisites

- Node.js 18+
- Cloudflare account

### Local Development

1. **Install dependencies**
   ```bash
   npm install
   ```

2. **Copy environment variables**
   ```bash
   cp cloudflare-api/.dev.vars.example cloudflare-api/.dev.vars
   # Edit .dev.vars with your Cloudflare credentials
   ```

3. **Initialize local D1 database**
   ```bash
   npm run cf:d1:init
   ```

4. **Start development servers**
   ```bash
   npm run cf:dev      # Terminal 1: Worker at http://127.0.0.1:8787
   npm run frontend:dev # Terminal 2: Frontend at http://127.0.0.1:3000
   ```

5. **Access the app**
   Open `http://127.0.0.1:3000` in your browser.

---

## API Reference

### Public Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/stats` | Total generation count |
| GET | `/api/catalog` | Subjects & streams list |
| POST | `/api/log-generation` | Log a generation event |

### Admin Endpoints (Requires Authentication)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/subjects` | List subjects |
| POST | `/admin/subjects` | Add subject |
| PUT | `/admin/subjects/:id` | Update subject |
| DELETE | `/admin/subjects/:id` | Delete subject |
| GET | `/admin/streams` | List streams |
| POST | `/admin/streams` | Add stream |
| DELETE | `/admin/streams/:id` | Delete stream |
| GET | `/admin/logs` | View generation logs |

---

## Deployment

1. **Create D1 database**
   ```bash
   cd cloudflare-api
   npx wrangler d1 create frontpage-db
   ```

2. **Update wrangler.toml**
   Add the database ID to `wrangler.toml` under the D1 binding.

3. **Apply schema**
   ```bash
   npx wrangler d1 execute frontpage-db --remote --file=./schema.sql
   ```

4. **Set secrets**
   ```bash
   npx wrangler secret put CLOUDFLARE_ACCOUNT_ID
   npx wrangler secret put BROWSER_RENDERING_API_TOKEN
   ```

5. **Deploy Worker**
   ```bash
   npx wrangler deploy
   ```

6. **Deploy to Cloudflare Pages**
   - Upload `index.html` and `static/` folder to Cloudflare Pages
   - Note the Pages URL
   - Open with: `https://your-pages-url?apiBase=https://your-worker.subdomain.workers.dev`

---

## Usage

1. Open the generator page
2. Fill in student details:
   - Name
   - Roll Number
   - Registration Number
   - Semester
   - Stream
   - Subject
3. Click "Generate Document" to download as PNG

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Built with ☕ and Cloudflare
</p>
