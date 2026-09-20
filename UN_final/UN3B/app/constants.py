"""Reference data shared by the API and (via GET /meta) the frontend.

Keeping these lists on the server means the profile form, the scheme admin form,
the validators and the rule engine can never drift apart.
"""

ROLES = ("user", "investor", "partner", "admin")
SELF_REGISTER_ROLES = ("user", "investor", "partner")  # admin is never self-service

GENDERS = ("Male", "Female", "Other")
CATEGORIES = ("General", "SC", "OBC", "Other")
STATES = ("Punjab", "Haryana", "Delhi", "Uttar Pradesh", "Rajasthan", "Maharashtra", "Other")
BUSINESS_TYPES = ("Manufacturing", "Services", "Retail", "Food", "Agriculture Allied", "Street Vendor", "Other")
BUSINESS_STAGES = ("Idea", "New Business", "Existing Business", "Expansion")

# slug -> human label. The slug is what is stored and sent over the API.
DOCUMENT_TYPES = {
    "identity_proof": "Identity Proof",
    "pan": "PAN",
    "income_certificate": "Income Certificate",
    "caste_certificate": "Caste Certificate",
    "business_registration": "Business Registration",
    "bank_statement": "Bank Statement",
    "project_report": "Project Report",
    "education_skill_certificate": "Education/Skill Certificate",
}

# value -> label, in pipeline order (the frontend draws its progress bar from this order)
APPLICATION_STATUSES = {
    "not_started": "Not Started",
    "documents_pending": "Documents Pending",
    "applied": "Applied",
    "under_review": "Under Review",
    "approved": "Approved",
    "rejected": "Rejected",
}
# statuses meaning "nothing has been submitted to the official portal yet"
PRE_SUBMISSION_STATUSES = ("not_started", "documents_pending")

ELIGIBILITY_STATUSES = ("eligible", "potentially_eligible", "not_eligible")
ELIGIBILITY_RANK = {"eligible": 2, "potentially_eligible": 1, "not_eligible": 0}

# Upload rules
ALLOWED_UPLOAD_KINDS = {
    # detected kind -> (canonical extension, served content-type)
    "pdf": (".pdf", "application/pdf"),
    "png": (".png", "image/png"),
    "jpeg": (".jpg", "image/jpeg"),
    "text": (".txt", "text/plain; charset=utf-8"),
}
