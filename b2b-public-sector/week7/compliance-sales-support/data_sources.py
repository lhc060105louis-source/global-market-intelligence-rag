# -*- coding: utf-8 -*-
"""Catalog of public sources compiled from the team's Week 1–2 research.

Fields: name, url, type, frequency, access, free, module, and notes.
"""
SOURCES = [
    # Regulations and policy
    {"name": "EUR-Lex European Union Legal Database", "url": "https://eur-lex.europa.eu", "type": "Regulation Text",
     "frequency": "Updated as regulations are enacted", "access": "API / Web Search", "free": True,
     "module": "Regulations and Policy", "notes": "Official legal texts searchable by identifier, date, and topic; RSS feeds are available."},
    {"name": "European Commission Policy Pages", "url": "https://commission.europa.eu", "type": "Policy Announcements",
     "frequency": "As needed", "access": "Web / News Feeds", "free": True,
     "module": "Regulations and Policy", "notes": "Official policy context for major regulations, including the Battery Regulation, AFIR, and AI Act."},
    {"name": "UNECE WP.29 Vehicle Regulations", "url": "https://unece.org/transport/wp29", "type": "Vehicle Technical Regulations",
     "frequency": "As needed", "access": "Web Download", "free": True,
     "module": "Regulations and Policy", "notes": "Original UN regulations, including R155 (cybersecurity) and R156 (software updates)."},
    {"name": "UK Parliament Legislation Tracker", "url": "https://www.legislation.gov.uk", "type": "United Kingdom Regulations",
     "frequency": "Updated as legislation changes", "access": "API / Web", "free": True,
     "module": "Regulations and Policy", "notes": "The United Kingdom's independent post-Brexit regulatory system; RSS subscriptions can track topics."},
    # Industry data
    {"name": "ACEA European Automobile Manufacturers Association", "url": "https://www.acea.auto", "type": "Registrations / Market Share",
     "frequency": "Monthly / Quarterly", "access": "Web / Report Download", "free": True,
     "module": "Industry Data", "notes": "EU passenger and commercial vehicle registrations, powertrain mix, and vehicle parc data."},
    {"name": "European Alternative Fuels Observatory (EAFO)", "url": "https://alternative-fuels-observatory.ec.europa.eu", "type": "Charging Infrastructure",
     "frequency": "Updated monthly", "access": "Web / Interactive Dashboard", "free": True,
     "module": "Industry Data", "notes": "EU27 public charging points, heavy-duty vehicle charging networks, and alternative-fuel vehicle data."},
    {"name": "Euro NCAP Safety Ratings", "url": "https://www.euroncap.com", "type": "Safety Assessment",
     "frequency": "Annual / Protocol Updates", "access": "Web", "free": True,
     "module": "Industry Data", "notes": "A four-phase rating system starting in 2026; useful for competitor safety benchmarking."},
    {"name": "J.D. Power IQS / CSI", "url": "https://www.jdpower.com", "type": "Quality / Satisfaction",
     "frequency": "Annual", "access": "Report Purchase / Secondary Sources", "free": False,
     "module": "Industry Data", "notes": "NEV-IQS reports are available for China; access to European data requires a company subscription."},
    {"name": "Autovista24 Residual Value Data", "url": "https://autovista24.autovistagroup.com", "type": "Used-Vehicle Residual Value",
     "frequency": "Monthly / Quarterly", "access": "Web", "free": True,
     "module": "Industry Data", "notes": "Three-year residual values by powertrain in Europe; some in-depth data requires a subscription."},
    # Public-sector opportunities
    {"name": "TED European Union Procurement Notices", "url": "https://ted.europa.eu", "type": "Government Procurement Notices",
     "frequency": "Updated daily", "access": "Web / RSS / API", "free": True,
     "module": "B2B and Public-Sector Opportunities", "notes": "EU public procurement portal with CPV codes, advanced search, and RSS feeds."},
    {"name": "GOV.UK Find a Tender", "url": "https://www.find-tender.service.gov.uk", "type": "United Kingdom Government Procurement",
     "frequency": "Updated daily", "access": "Web / API", "free": True,
     "module": "B2B and Public-Sector Opportunities", "notes": "UK public procurement platform covering LEVI charging and electric bus projects."},
    {"name": "Innovate UK Business Connect", "url": "https://iuk-business-connect.org.uk", "type": "Innovation Projects / Funding",
     "frequency": "Project-based", "access": "Web", "free": True,
     "module": "B2B and Public-Sector Opportunities", "notes": "Funding opportunities for charging, energy systems, and ultra-fast charging demonstrations."},
    {"name": "EU Publications Office Procurement Details", "url": "https://op.europa.eu/en/web/public-procurement", "type": "Public Procurement Details",
     "frequency": "As needed", "access": "Web", "free": True,
     "module": "B2B and Public-Sector Opportunities", "notes": "Project-level procurement details, including bus projects in North Macedonia and Romania."},
    # Competitors and markets
    {"name": "Reuters / JATO Market Analysis", "url": "https://www.reuters.com/business/autos-transportation/", "type": "Market Share / Competitors",
     "frequency": "Monthly / Quarterly", "access": "Web", "free": True,
     "module": "Competitors and Markets", "notes": "European market share for Chinese brands and registration data for brands such as BYD."},
    {"name": "ADAC Germany Vehicle Breakdown Statistics", "url": "https://www.adac.de/rund-ums-fahrzeug/tests/pannenstatistik/", "type": "Reliability Data",
     "frequency": "Annual", "access": "Web", "free": True,
     "module": "Competitors and Markets", "notes": "Authoritative German vehicle reliability data that can support after-sales credibility."},
    {"name": "European Council on Foreign Relations (ECFR)", "url": "https://ecfr.eu", "type": "Policy / Security Analysis",
     "frequency": "As needed", "access": "Web", "free": True,
     "module": "Competitors and Markets", "notes": "Policy analysis of Chinese EV data security and connected-vehicle security risks."},
    # Corporate procurement
    {"name": "Volkswagen Group Supplier Portal", "url": "https://supplier.volkswagen-group.com/", "type": "Supplier Portal",
     "frequency": "As needed", "access": "Web (Registration Required)", "free": True,
     "module": "Corporate Procurement", "notes": "Tracks procurement priorities for traction batteries and Unified Cell; not a public RFP source."},
    {"name": "Mercedes-Benz Supplier Portal", "url": "https://supplier.mercedes-benz.com/", "type": "Supplier Portal",
     "frequency": "As needed", "access": "Web (Registration Required)", "free": True,
     "module": "Corporate Procurement", "notes": "Tracks traction battery and joint research procurement priorities for premium electric models."},
    {"name": "Stellantis Supplier Portal", "url": "https://suppliers.stellantis.com/", "type": "Supplier Portal",
     "frequency": "As needed", "access": "Web (Registration Required)", "free": True,
     "module": "Corporate Procurement", "notes": "Tracks the LFP battery plant supply chain in Spain and potential joint-venture plant opportunities."},
    {"name": "Ford Supplier Portal", "url": "https://supplier.ford.com/", "type": "Supplier Portal",
     "frequency": "As needed", "access": "Web (Registration Required)", "free": True,
     "module": "Corporate Procurement", "notes": "Tracks traction battery and supply-chain procurement priorities for European electric commercial vehicles."},
]

# Sources grouped by module.
MODULES = ["Regulations and Policy", "Industry Data", "B2B and Public-Sector Opportunities", "Competitors and Markets", "Corporate Procurement"]

# Supported source access methods.
ACCESS_METHODS = ["API / Web Search", "API / Web", "Web", "Web / RSS / API", "Web / Report Download",
                  "Web / Interactive Dashboard", "Web / News Feeds", "Web (Registration Required)", "Web Download",
                  "Report Purchase / Secondary Sources"]
