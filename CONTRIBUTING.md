# Contributing to Respectlytics

Thank you for your interest in contributing to Respectlytics! We welcome contributions from the community.

## How to Contribute

### Reporting Bugs

1. Check [existing issues](https://github.com/respectlytics/respectlytics/issues) to avoid duplicates
2. Open a new issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, Docker version)

### Suggesting Features

Open an issue with the "Feature Request" label. Describe:
- The problem you're trying to solve
- Your proposed solution
- Alternative approaches you considered

### Submitting Code

1. **Fork** the repository
2. **Create a branch** from `main`: `git checkout -b feature/your-feature`
3. **Make your changes** following the code style guidelines below
4. **Test** your changes thoroughly
5. **Commit** with clear, descriptive messages
6. **Push** your branch and open a **Pull Request**

## Contributor License Agreement (CLA)

All contributors must sign a Contributor License Agreement (CLA) before their pull request can be merged. This is handled automatically via [cla-assistant.io](https://cla-assistant.io) — you'll be prompted when you open your first PR.

The CLA preserves our ability to offer dual licensing (AGPL-3.0 for open source, commercial for enterprises).

## Code Style Guidelines

### Python

- Follow Django conventions and PEP 8
- Use meaningful variable and function names
- Add docstrings for public functions and classes
- Keep functions focused — one function, one purpose

### Templates (HTML)

- **Tailwind CSS only** — do not create custom CSS rules
- Use the dark theme design system (`bg-slate-900`, `bg-[#1e293b]`, etc.)
- Follow existing template patterns in the repository

### JavaScript

- Vanilla JS preferred — no frameworks in templates
- Use `const` and `let`, not `var`
- Use `async/await` for async operations

## What Makes a Good PR

- **Focused:** One feature or fix per PR
- **Tested:** Include steps to verify the change
- **Documented:** Update docs if behavior changes
- **Clean:** No unrelated changes or formatting noise

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR-USERNAME/respectlytics.git
cd respectlytics

# Set up (see README.md for full instructions)
cp .env.example .env
docker compose up -d

# Create test user
docker compose exec web python manage.py createsuperuser
```

## Questions?

- Open a [Discussion](https://github.com/respectlytics/respectlytics/discussions)
- Email: [respectlytics@loheden.com](mailto:respectlytics@loheden.com)

---

Thank you for helping make privacy-first analytics accessible to everyone!
