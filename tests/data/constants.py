"""Facts about the seeded fixture set, stated once.

Everything here mirrors `api/app/seed.py` in the `engage-app` repository. A test that needs "an id belonging to
the other tenant" should say so by name rather than hardcoding 41 in six files,
so that when the seed changes there is one place to follow it.

Note what is deliberately *absent*: counts. `ACME_CONTACT_COUNT = 40` would be
true only until another worker inserts a row, and a test asserting on it would
pass alone and fail at `-n 4`. See Part 2.1 of FRAMEWORK_BUILD.md.
"""

# Contact id ranges are fixed per tenant in the seed, which is what makes
# cross-tenant tests possible: an acme token asking for ACME_CONTACT_ID is a
# legitimate read, and asking for GLOBEX_CONTACT_ID must not be.
ACME_CONTACT_ID = 1
GLOBEX_CONTACT_ID = 41

# Seeded segments (acme unless noted).
SEGMENT_ENTERPRISE_RULE = 1
SEGMENT_HIGH_VALUE_RULE = 2
SEGMENT_VIP_STATIC = 3
SEGMENT_GLOBEX_FREE = 4

# Seeded campaigns, one per interesting state.
CAMPAIGN_DRAFT = 1
CAMPAIGN_SCHEDULED = 2
CAMPAIGN_SENT = 3
CAMPAIGN_GLOBEX_DRAFT = 4
CAMPAIGN_GLOBEX_RUNNING = 5

# The application's pagination contract: GET /api/contacts?size= is capped.
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20
