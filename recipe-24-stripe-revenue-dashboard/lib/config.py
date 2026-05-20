from __future__ import annotations

import os

USE_STRIPE_MOCK = os.environ.get("STRIPE_MOCK", "").lower() in {"1", "true", "yes"}
