"""Seed reference data (schemes, partners) and, in development, demo accounts.

    python -m app.seed            # idempotent: only fills empty tables / missing demo users
    python -m app.seed --reset    # DROP everything and reseed (development only!)

Reference data is only inserted into an EMPTY table, so edits an admin makes through the API
are never overwritten on restart.
"""
import argparse
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import Base, SessionLocal, engine
from .models import Partner, Scheme, User, utcnow
from .security import hash_password

log = logging.getLogger("udyam.seed")

ALL_CATEGORIES = ["General", "SC", "OBC", "Other"]

SCHEMES = [
    dict(
        id="pmegp", name="PMEGP", full_name="Prime Minister\u2019s Employment Generation Programme",
        scheme_type="Credit-linked subsidy",
        description="Supports new micro-enterprises through bank finance and margin-money subsidy.",
        min_amount=100_000, max_amount=5_000_000, eligible_categories=ALL_CATEGORIES,
        business_types=["Manufacturing", "Services", "Retail", "Food", "Agriculture Allied"],
        business_stages=["Idea", "New Business"],
        max_income=None, min_age=18, education="No minimum qualification prescribed for the general category",
        purpose="Setting up new micro-enterprises (manufacturing/service)",
        interest_rate="As charged by the financing bank (not centrally fixed) \u2014 verify current rate with your bank",
        own_contribution_pct=0.10,
        application_channel="Nearest scheduled bank branch / KVIC, KVIB or DIC via the PMEGP e-portal",
        required_documents=["identity_proof", "pan", "income_certificate", "caste_certificate",
                            "business_registration", "bank_statement", "project_report"],
        benefits="Margin-money subsidy; bank finance; entrepreneurship support.",
        source="KVIC / Ministry of MSME",
        official_url="https://www.kviconline.gov.in/pmegpeportal/pmegphome/index.jsp",
    ),
    dict(
        id="mudra", name="PMMY / MUDRA", full_name="Pradhan Mantri Mudra Yojana", scheme_type="Collateral-free credit",
        description="Institutional credit for micro enterprises and eligible non-farm income-generating activities.",
        min_amount=10_000, max_amount=2_000_000, eligible_categories=ALL_CATEGORIES,
        business_types=["Manufacturing", "Services", "Retail", "Food", "Agriculture Allied", "Street Vendor"],
        business_stages=["Idea", "New Business", "Existing Business", "Expansion"],
        max_income=None, min_age=18, education="No minimum qualification prescribed",
        purpose="Working capital or term loan for non-farm income-generating activity",
        interest_rate="Market-linked, set by the lending bank/NBFC/MFI \u2014 no fixed central rate",
        own_contribution_pct=0.10,
        application_channel="Any scheduled bank, NBFC or MFI via the PMMY / Jan Samarth portal",
        required_documents=["identity_proof", "pan", "bank_statement", "project_report"],
        benefits="Shishu, Kishore, Tarun and Tarun Plus categories; collateral not required.",
        source="Department of Financial Services, Ministry of Finance",
        official_url="https://financialservices.gov.in/index.php/pradhan-mantri-mudra-yojana-pmmy",
    ),
    dict(
        id="svanidhi", name="PM SVANidhi", full_name="Prime Minister Street Vendor\u2019s AtmaNirbhar Nidhi",
        scheme_type="Working-capital loan",
        description="Credit support designed for eligible street vendors.",
        min_amount=5_000, max_amount=50_000, eligible_categories=ALL_CATEGORIES,
        business_types=["Street Vendor"], business_stages=["New Business", "Existing Business"],
        max_income=None, min_age=18, education="No minimum qualification prescribed",
        purpose="Working capital for street vending",
        interest_rate="As charged by the lending institution, with interest subsidy on timely repayment",
        own_contribution_pct=0.0,
        application_channel="Urban Local Body-issued vending certificate/ID holders, via the PM SVANidhi portal",
        required_documents=["identity_proof", "bank_statement"],
        benefits="Working-capital support for eligible street vendors; lender terms apply.",
        source="Ministry of Housing & Urban Affairs", official_url="https://pmsvanidhi.mohua.gov.in/",
    ),
]

# Coordinates are APPROXIMATE demo values (district headquarters area), not surveyed office
# locations -- replace them with real branch coordinates before relying on the locator.
PARTNERS = [
    dict(name="State Bank of India", partner_type="Public Sector Bank", state=None, coverage="Pan India",
         supported_scheme_ids=["pmegp", "mudra"], notes="MSME credit", website_url="https://sbi.co.in/"),
    dict(name="Punjab National Bank", partner_type="Public Sector Bank", state=None, coverage="Pan India",
         supported_scheme_ids=["pmegp", "mudra"], notes="MSME credit", website_url="https://www.pnbindia.in/"),
    dict(name="Bank of Baroda", partner_type="Public Sector Bank", state=None, coverage="Pan India",
         supported_scheme_ids=["pmegp", "mudra"], notes="MSME credit", website_url="https://www.bankofbaroda.in/"),
    dict(name="JanSamarth", partner_type="Government credit portal", state=None, coverage="India",
         supported_scheme_ids=[], notes="Multiple credit-linked government schemes", website_url="https://www.jansamarth.in/"),
    dict(name="Punjab Gramin Bank", partner_type="Regional Rural Bank", state="Punjab", district="Kapurthala",
         latitude=31.38, longitude=75.38, coverage="Punjab districts",
         supported_scheme_ids=["pmegp", "mudra"], website_url="https://pgb.co.in/"),
    dict(name="Delhi Financial Corporation", partner_type="State Financial Corporation", state="Delhi",
         district="New Delhi", latitude=28.61, longitude=77.21, coverage="NCT of Delhi",
         supported_scheme_ids=["pmegp"], notes="MSME term loans", website_url="https://www.dfc.co.in/"),
]


def seed_reference_data(db: Session) -> None:
    if db.scalar(select(Scheme.id).limit(1)) is None:
        base = utcnow()
        for i, data in enumerate(SCHEMES):
            # explicit, increasing timestamps keep the original list order (ranking ties depend on it)
            db.add(Scheme(**data, created_at=base + timedelta(seconds=i)))
        log.info("Seeded %d schemes", len(SCHEMES))
    if db.scalar(select(Partner.id).limit(1)) is None:
        base = utcnow()
        for i, data in enumerate(PARTNERS):
            db.add(Partner(**data, verified=False, created_at=base + timedelta(seconds=i)))
        log.info("Seeded %d partners", len(PARTNERS))
    db.commit()


def _ensure_user(db: Session, email: str, password: str, full_name: str, role: str) -> None:
    if db.scalar(select(User.id).where(User.email == email)) is None:
        db.add(User(email=email, full_name=full_name, role=role, password_hash=hash_password(password)))
        log.info("Created %s account %s", role, email)


def seed_accounts(db: Session) -> None:
    s = get_settings()
    if s.seed_demo_user:
        _ensure_user(db, s.demo_user_email, s.demo_user_password, "Demo User", "user")
    if s.admin_password:
        _ensure_user(db, s.admin_email, s.admin_password, "Admin", "admin")
    elif s.environment != "production":
        log.warning("ADMIN_PASSWORD not set -- using the insecure demo admin password 'admin123' (development only).")
        _ensure_user(db, s.admin_email, "admin123", "Admin", "admin")
    else:
        log.warning("ADMIN_PASSWORD not set in production -- no admin account was created.")
    db.commit()


def run_seed() -> None:
    with SessionLocal() as db:
        seed_reference_data(db)
        seed_accounts(db)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Seed the Udyam-Nirdesh database")
    parser.add_argument("--reset", action="store_true", help="drop ALL tables first (development only)")
    args = parser.parse_args()
    if args.reset:
        if get_settings().environment == "production":
            raise SystemExit("Refusing to --reset in production.")
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    run_seed()


if __name__ == "__main__":
    main()
