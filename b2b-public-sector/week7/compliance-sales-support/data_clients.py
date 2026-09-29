# -*- coding: utf-8 -*-
"""Customer support seed data aligned with the PRD client profiles and demo scenarios.

Each customer type has a profile card with a description, pain points, procurement priorities,
product and technology solutions, services, case studies, evidence, talking points, and related
business scenarios for regulation-gap matching. `case_verified` marks whether a case has a reliable
source; unverified cases must not be presented as successful references (PRD FR-11).
"""

# Customer type values (PRD client_type).
CLIENT_TYPES = ["Government", "Public Transit Operator", "Logistics Fleet", "Corporate Fleet", "Mobility Platform"]
# Application scenarios aligned with the regulation scenario values.
APP_SCENARIOS = ["Public Transit Operator", "Logistics Fleet", "Corporate Fleet", "Government", "Mobility Platform", "Charging Infrastructure"]
# Procurement priorities used for filtering and solution matching.
FOCUS_POINTS = ["Total Cost of Ownership (TCO)", "Compliance and ESG", "Local Employment and Social Value", "Data Security and Sovereignty",
                "Vehicle Reliability and Availability", "Range and Charging", "Residual Value and Buyback", "Maintenance SLA", "Safety Rating"]

CLIENTS = [
  {
    "client_key": "gov",
    "client_id": "C-GOV",
    "client_type": "Government",
    "sample_name": "European City Transport Authority (Government / Municipal Example)",
    "region": "Germany / United Kingdom",
    "scenario": "Public Transit Operator",
    "portrait": "Municipal or regional government and transport authorities responsible for public fleets, city buses, sanitation, and postal electrification. Procures through published TED/OJEU tenders.",
    "painpoints": ["Pressure to reduce emissions", "Need to demonstrate local employment and social value", "High sensitivity to data security and sovereignty", "Need auditable whole-life costs (TCO)"],
    "focus": ["Compliance and ESG", "Local Employment and Social Value", "Total Cost of Ownership (TCO)", "Data Security and Sovereignty", "Safety Rating"],
    "product": ["Battery-electric bus and government vehicle fleets", "Local assembly with partner-provided core electric powertrain technology", "Integrated vehicle, charging, and operations solution"],
    "tech": ["Battery passport and carbon-footprint data pack", "CSMS (R155) cybersecurity system and TARA", "EU data residency and localized data architecture"],
    "service": ["Local maintenance-network commitment and SLA", "Driver training and knowledge transfer", "Residual-value / buyback support and green procurement response"],
    "cases": [
      {"title": "BYD–ADL London Electric Buses (TfL 2030 Zero-Emission Goal)", "detail": "BYD supplies batteries, electric drivetrains, and electric chassis; ADL handles local bodywork and assembly in the UK. The program began with 51 buses in 2015 and reached its 1,500th delivery by 2023. Go-Ahead London has received or ordered more than 577 buses and ordered about 299 more. The market-entry model combines technology transfer, local manufacturing, operational validation, and policy alignment.", "verified": True, "source": "Alexander Dennis / TfL public news"},
    ],
    "evidence": ["Euro NCAP five-star rating", "Battery passport and carbon-footprint declaration", "CSMS certificate and data-residency statement", "Local assembly and employment commitment"],
    "talking_points": "“Verifiable compliance, EU-based data, and local value.” Use safety ratings, battery passports, and CSMS evidence to answer safety reviews, and local partnerships to address industrial-policy priorities.",
    "link_regulations": ["REG-001", "REG-004", "REG-006", "REG-010", "REG-011", "REG-016"],
  },
  {
    "client_key": "bus",
    "client_id": "C-BUS",
    "client_type": "Public Transit Operator",
    "sample_name": "Regional Bus Operator Example",
    "region": "United Kingdom / Netherlands",
    "scenario": "Public Transit Operator",
    "portrait": "Urban and regional bus operators such as Go-Ahead, with fleets of hundreds or thousands of vehicles. Priorities include electrification, depot-charging upgrades, and fixed-route operations.",
    "painpoints": ["Sensitive to per-kilometre and whole-life costs", "Vehicle reliability and availability are critical", "Winter range and depot-charging schedules", "Spare-parts and repair response, residual value and buyback"],
    "focus": ["Vehicle Reliability and Availability", "Total Cost of Ownership (TCO)", "Range and Charging", "Maintenance SLA", "Residual Value and Buyback"],
    "product": ["Single- and double-deck battery-electric buses", "Depot charging and energy management", "Bundled vehicle, charger, and maintenance offer"],
    "tech": ["Measured energy consumption and range, including winter conditions", "Battery warranty, state of health, and battery passport", "Charging schedules and depot sizing"],
    "service": ["Spare-parts lead times and local repair network", "Operations dashboard for availability and fault rates", "Battery buyback and residual-value options"],
    "cases": [
      {"title": "BYD–ADL / Go-Ahead London Repeat Orders", "detail": "From a 51-bus pilot to more than 1,500 deliveries overall, Go-Ahead London has received or ordered more than 577 buses and ordered about 299 more. Repeat orders provide evidence of reliability and manageable operating costs.", "verified": True, "source": "Alexander Dennis public news"},
    ],
    "evidence": ["Reliability, fault-rate, and availability data", "Measured energy-consumption and range report", "Battery warranty, state of health, and passport", "TCO calculation"],
    "talking_points": "“Repeat orders are the strongest reference.” Use operational data and repeat orders to address reliability concerns; package vehicles with charging, maintenance, and buyback.",
    "link_regulations": ["REG-001", "REG-002", "REG-004", "REG-008", "REG-010", "REG-011"],
  },
]
CLIENTS += [
  {
    "client_key": "log",
    "client_id": "C-LOG",
    "client_type": "Logistics Fleet",
    "sample_name": "European Urban Delivery and Parcel Fleet Example",
    "region": "France / Germany",
    "scenario": "Logistics Fleet",
    "portrait": "Urban delivery and parcel companies such as DHL or DPD, operating vans, trucks, and heavy-duty vehicles for last-mile and long-haul routes, including low-emission zones (LEZs).",
    "painpoints": ["Per-kilometre cost and energy use", "Balancing range, payload, and charging time", "LEZ eligibility", "Vehicle availability and highway charging (AFIR)"],
    "focus": ["Total Cost of Ownership (TCO)", "Range and Charging", "Vehicle Reliability and Availability", "Compliance and ESG"],
    "product": ["Battery-electric urban-delivery vans and light trucks", "Highway fast charging and energy solutions", "Separate vehicle configurations for urban delivery and long-haul routes"],
    "tech": ["Range, payload, and charging compatibility data", "800 V fast charging for AFIR corridors", "Connected-vehicle data integration with TMS, with data-compliance controls"],
    "service": ["Per-kilometre cost comparison and availability commitment", "Repair response and spare parts", "CO₂ compliance and LEZ access support"],
    "cases": [
      {"title": "Potential Case: Chinese Electric Delivery Vans in Europe", "detail": "A possible urban and long-haul logistics pilot combined with AFIR corridor fast charging. This is a conceptual example, not a verified public project; add a real RFP identifier and operating data before presentation.", "verified": False, "source": "Unverified"},
    ],
    "evidence": ["Measured range, payload, and energy use", "Charging and energy plan", "Availability and repair response", "CO₂ compliance and LEZ access", "Total cost calculation"],
    "talking_points": "“Every kilometre counts; uptime wins.” Lead with per-kilometre cost and availability, and show how 800 V charging supports AFIR corridors and LEZ access.",
    "link_regulations": ["REG-002", "REG-004", "REG-007", "REG-008", "REG-009", "REG-010"],
  },
  {
    "client_key": "ent",
    "client_id": "C-ENT",
    "client_type": "Corporate Fleet",
    "sample_name": "Multinational Company or Leasing Fleet Example",
    "region": "Germany / Netherlands",
    "scenario": "Corporate Fleet",
    "portrait": "Multinational and large-company fleets for business travel and commuting, as well as leasing firms such as Ayvens. Use cases include company cars, employee commuting, and ESG emissions reduction, often financed through leasing.",
    "painpoints": ["Residual value and monthly lease payments", "ESG and corporate carbon reporting", "TCO and tax treatment", "Employee experience and data privacy"],
    "focus": ["Residual Value and Buyback", "Compliance and ESG", "Total Cost of Ownership (TCO)", "Data Security and Sovereignty", "Safety Rating"],
    "product": ["Battery-electric company and commuter vehicle mix", "Finance lease with residual-value buyback", "Corporate ESG fleet emissions package"],
    "tech": ["Residual-value forecast and buyback commitment", "Carbon-footprint and ESG scope data", "GDPR-compliant employee data handling"],
    "service": ["TCO and tax analysis", "Employee experience and safety guidance", "Fleet management and maintenance network"],
    "cases": [
      {"title": "Potential Case: European Leasing or Corporate Fleet Partnership", "detail": "A possible corporate ESG fleet-emissions reduction case. This is a conceptual example, not a verified public project.", "verified": False, "source": "Unverified"},
    ],
    "evidence": ["Residual-value forecast and buyback commitment", "Carbon-footprint and ESG data pack", "Euro NCAP five-star rating", "GDPR-compliant employee data handling", "TCO and tax analysis"],
    "talking_points": "“Strengthen ESG reporting and employee retention.” Use carbon data to support scope reporting and residual-value protection to address depreciation concerns.",
    "link_regulations": ["REG-001", "REG-003", "REG-006", "REG-008", "REG-009", "REG-013"],
  },
  {
    "client_key": "mob",
    "client_id": "C-MOB",
    "client_type": "Mobility Platform",
    "sample_name": "Ride-Hailing, Taxi, or Shared-Mobility Platform Example",
    "region": "France / Spain",
    "scenario": "Mobility Platform",
    "scenario": "Mobility Platform",
    "portrait": "Ride-hailing, taxi, and shared-mobility platforms with passenger-car fleets used intensively in cities and airport services. Priorities include fleet electrification and urban operations.",
    "painpoints": ["Whole-life cost and residual value under high mileage", "High-mileage durability and battery degradation", "Fast-charging access and vehicle downtime", "Passenger experience, safety, and fleet financing"],
    "focus": ["Total Cost of Ownership (TCO)", "Residual Value and Buyback", "Range and Charging", "Vehicle Reliability and Availability", "Data Security and Sovereignty"],
    "product": ["Durable battery-electric passenger cars", "Bulk procurement and financing options", "Fast-charging and energy-network integration"],
    "tech": ["High-mileage durability, battery degradation (state of health), and battery passports", "Fast-charging and energy network", "Platform data compliance for the Data Act and AI Act"],
    "service": ["High-mileage TCO and residual-value analysis", "Bulk procurement financing and buyback", "Durability and battery warranty"],
    "cases": [
      {"title": "Potential Case: Electric Ride-Hailing or Taxi Fleet", "detail": "A possible example is BYD taxis operating in multiple markets or on fixed airport routes. This is a conceptual example; add a verified project and operating data before presentation.", "verified": False, "source": "Unverified"},
    ],
    "evidence": ["High-mileage durability, battery degradation, and battery passport", "Fast-charging and energy network", "Residual value and buyback terms", "Euro NCAP rating", "Bulk procurement financing plan"],
    "talking_points": "“Intensive use is the strongest proof.” Use high-mileage durability and fast charging to reduce downtime and energy costs, and bulk financing with buyback to ease capital pressure.",
    "link_regulations": ["REG-001", "REG-003", "REG-004", "REG-006", "REG-010", "REG-014"],
  },
]
