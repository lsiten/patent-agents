"""Environment and runtime file constants."""

from __future__ import annotations

ENV_DEVELOPMENT = "development"
ENV_TESTING = "testing"
ENV_STAGING = "staging"
ENV_PRODUCTION = "production"

DEFAULT_ENVIRONMENT = ENV_DEVELOPMENT

ENV_FILE_BY_ENVIRONMENT = {
    ENV_DEVELOPMENT: ".env",
    ENV_TESTING: ".env.testing",
    ENV_PRODUCTION: ".env.production",
}

