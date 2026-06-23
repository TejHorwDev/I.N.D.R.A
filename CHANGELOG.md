# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-06-22

### Added
- **Docker Support**: Added `Dockerfile` and `docker-compose.yml`.
- **CI/CD**: Added GitHub Actions pipeline for linting and testing.
- **Testing**: Added `pytest` framework with core suite.
- **Core Abstraction**: Created `core/utils.py` for centralizing config and logging.

### Changed
- **Performance**: Abstracted duplicate initialization logic across `actions/` modules.
- **Code Quality**: Applied strict PEP8 formatting (`black`, `isort`) to all python modules.
- **UI Tweaks**: Suppressed Qt High-DPI and Font environment spam.
- **Security**: Moved hardcoded secrets out of the codebase in favor of `.env` patterns.

### Fixed
- Fixed legacy `Image.LANCZOS` deprecation in `file_processor.py`.
- Fixed numerous duplicate code blocks and unhandled exceptions in action runners.
