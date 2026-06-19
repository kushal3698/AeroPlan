import os
import re
import urllib.parse
import wikipedia
import requests
import ssl
import urllib3
try:
    ssl._create_default_https_context = ssl._create_unverified_context
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass
import urllib.parse
import wikipedia
import requests
from typing import Literal, TypedDict, List
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# 1. Define the System State
class AgentState(TypedDict):
    messages: List[str]
    destination: str
    duration_days: int
    interests: List[str]
    budget_limit: float
    currency: str
    language: str
    research_notes: str
    budget_notes: str
    final_itinerary: str
    next_step: str

# Exchange rates relative to 1 USD
exchange_rates = {
    "USD": (1.0, "$"),
    "EUR": (0.92, "\u20ac"),
    "JPY": (155.0, "\u00a5"),
    "GBP": (0.79, "\u00a3"),
    "INR": (83.5, "\u20b9"),
    "CAD": (1.37, "C$")
}

# Fact-Checking Database for popular travel attractions
REAL_WORLD_COST_DB = {
    "wonderla": {"cost_usd": 15.0, "notes": "Ticket price is approx. 1200-1500 INR"},
    "eiffel tower": {"cost_usd": 25.0, "notes": "Standard ticket to summit"},
    "louvre": {"cost_usd": 24.0, "notes": "Louvre Museum entry"},
    "disneyland": {"cost_usd": 60.0, "notes": "1-day passport ticket"},
    "universal studios": {"cost_usd": 65.0, "notes": "1-day pass"},
    "taj mahal": {"cost_usd": 15.0, "notes": "Foreign tourist ticket"},
    "empire state": {"cost_usd": 44.0, "notes": "86th floor observatory ticket"},
    "statue of liberty": {"cost_usd": 24.0, "notes": "Ferry and pedestal ticket"},
    "london eye": {"cost_usd": 45.0, "notes": "Standard entry ticket"},
    "colosseum": {"cost_usd": 20.0, "notes": "Standard entry ticket"},
    "sagrada": {"cost_usd": 28.0, "notes": "Temple entry ticket"},
    "sydney opera house": {"cost_usd": 30.0, "notes": "Standard guided tour"},
    "fushimi inari": {"cost_usd": 0.0, "notes": "Free entry"},
    "kinkaku-ji": {"cost_usd": 3.5, "notes": "Temple entry ticket"},
    "kiyomizu-dera": {"cost_usd": 3.0, "notes": "Temple entry ticket"},
    "arashiyama": {"cost_usd": 0.0, "notes": "Free entry"}
}

# Average daily baseline costs (USD) in popular cities to scale realistically
CITY_COST_PROFILES = {
    "new york": {"lodging": 180.0, "dining": 60.0, "transit": 15.0, "activities": 35.0},
    "london": {"lodging": 140.0, "dining": 50.0, "transit": 15.0, "activities": 30.0},
    "paris": {"lodging": 130.0, "dining": 50.0, "transit": 12.0, "activities": 25.0},
    "tokyo": {"lodging": 110.0, "dining": 45.0, "transit": 10.0, "activities": 25.0},
    "rome": {"lodging": 100.0, "dining": 45.0, "transit": 8.0, "activities": 20.0},
    "sydney": {"lodging": 120.0, "dining": 50.0, "transit": 12.0, "activities": 25.0},
    "barcelona": {"lodging": 95.0, "dining": 40.0, "transit": 8.0, "activities": 20.0},
    "kyoto": {"lodging": 90.0, "dining": 40.0, "transit": 10.0, "activities": 15.0},
    "delhi": {"lodging": 35.0, "dining": 15.0, "transit": 5.0, "activities": 8.0},
    "mumbai": {"lodging": 45.0, "dining": 18.0, "transit": 6.0, "activities": 10.0},
    "bangalore": {"lodging": 40.0, "dining": 16.0, "transit": 5.0, "activities": 10.0},
    "kochi": {"lodging": 30.0, "dining": 12.0, "transit": 4.0, "activities": 8.0}
}

def get_fact_checked_activity_cost(attraction_name, default_cost, sym, rate):
    attr_lower = attraction_name.lower()
    for key, val in REAL_WORLD_COST_DB.items():
        if key in attr_lower:
            real_cost_usd = val["cost_usd"]
            # Convert to target currency based on exchange rate
            real_cost = int(real_cost_usd * rate)
            return real_cost
    return default_cost

# Translation structures for Mock LLM fallbacks
english_defaults = {
    "research_title": "### \U0001f5fa\ufe0f Research Summary for {destination}",
    "interests_label": "Tailored to interests: {interests}",
    "attractions_title": "#### \U0001f31f Top Attractions",
    "culinary_title": "#### \U0001f35c Culinary Highlights & Street Food",
    "tips_title": "#### \U0001f4a1 Local Travel Tips",
    "budget_title": "### \U0001f4b0 Budget Estimate for {duration} Days in {destination}",
    "est_total": "- **Estimated Total Cost**: {sym}{total} per person",
    "limit_label": "- **Budget Limit**: {sym}{limit}",
    "status_label": "- **Status**: {status}",
    "within_budget": "Within budget",
    "exceeds_budget": "Exceeds budget",
    "table_headers": "| Category | Cost per Day ({curr}) | Total Cost ({curr}) | Details |",
    "categories": {
        "Accommodation": "Accommodation",
        "Dining & Drinks": "Dining & Drinks",
        "Transit": "Transit",
        "Activities & Entry": "Activities & Entry",
        "Miscellaneous": "Miscellaneous",
        "Total": "Total"
    },
    "saving_tips_title": "#### \U0001f4b8 Budget Saving Tips",
    "itinerary_title": "# \u2708\ufe0f Complete Travel Itinerary: {duration} Days in {destination}",
    "day_label": "\U0001f4c5 Day {d}",
    "morning": "Morning",
    "lunch": "Lunch",
    "afternoon": "Afternoon",
    "evening": "Evening",
    "checklist_title": "### \U0001f392 Final Travel Checklist"
}

translations = {
    "Spanish": {
        "research_title": "### \U0001f5fa\ufe0f Resumen de Investigaci\u00f3n para {destination}",
        "interests_label": "Adaptado a intereses: {interests}",
        "attractions_title": "#### \U0001f31f Principales Atracciones",
        "culinary_title": "#### \U0001f35c Aspectos Culinarios Destacados y Comida Callejera",
        "tips_title": "#### \U0001f4a1 Consejos de Viaje Locales",
        "budget_title": "### \U0001f4b0 Estimaci\u00f3n de Presupuesto para {duration} D\u00edas en {destination}",
        "est_total": "- **Costo Total Estimado**: {sym}{total} por persona",
        "limit_label": "- **L\u00edmite de Presupuesto**: {sym}{limit}",
        "status_label": "- **Estado**: {status}",
        "within_budget": "Dentro del presupuesto",
        "exceeds_budget": "Excede el presupuesto",
        "table_headers": "| Categor\u00eda | Costo por D\u00eda ({curr}) | Costo Total ({curr}) | Detalles |",
        "categories": {
            "Accommodation": "Alojamiento",
            "Dining & Drinks": "Comidas y Bebidas",
            "Transit": "Transporte",
            "Activities & Entry": "Actividades y Entradas",
            "Miscellaneous": "Varios",
            "Total": "Total"
        },
        "saving_tips_title": "#### \U0001f4b8 Consejos para Ahorrar Presupuesto",
        "itinerary_title": "# \u2708\ufe0f Itinerario de Viaje Completo: {duration} D\u00edas en {destination}",
        "day_label": "\U0001f4c5 D\u00eda {d}",
        "morning": "Ma\u00f1ana",
        "lunch": "Almuerzo",
        "afternoon": "Tarde",
        "evening": "Noche",
        "checklist_title": "### \U0001f392 Lista de Verificaci\u00f3n de Viaje Final"
    },
    "Japanese": {
        "research_title": "### \U0001f5fa\ufe0f {destination}\u306e\u8abf\u67fb\u6982\u8981",
        "interests_label": "\u8208\u5473\u306b\u5408\u308f\u305b\u305f\u30d7\u30e9\u30f3: {interests}",
        "attractions_title": "#### \U0001f31f \u4e3b\u306a\u89b3\u5149\u30b9\u30dd\u30c3\u30c8",
        "culinary_title": "#### \U0001f35c \u30b0\u30eb\u30e1\u3068\u30b9\u30c8\u30ea\u30fc\u30c8\u30d5\u30fc\u30c9",
        "tips_title": "#### \U0001f4a1 \u73fe\u5730\u65c5\u884c\u306e\u30d2\u30f3\u30c8",
        "budget_title": "### \U0001f4b0 {destination}\u65c5\u884c\u306b\u304b\u304b\u308b\u4e88\u7b97\uff08{duration}\u65e5\u9593\uff09",
        "est_total": "- **\u63a8\u5b9a\u5408\u8a08\u8cbb\u7528**: 1\u4eba\u3042\u305f\u308a {sym}{total}",
        "limit_label": "- **\u4e88\u7b97\u5236\u9650**: {sym}{limit}",
        "status_label": "- **\u30b9\u30c6\u30fc\u30bf\u30b9**: {status}",
        "within_budget": "\u4e88\u7b97\u5185",
        "exceeds_budget": "\u4e88\u7b97\u30aa\u30fc\u30d0\u30fc",
        "table_headers": "| \u30ab\u30c6\u30b4\u30ea | 1\u65e5\u3042\u305f\u308a\u306e\u8cbb\u7528 ({curr}) | \u5408\u8a08\u8cbb\u7528 ({curr}) | \u8a73\u7d30 |",
        "categories": {
            "Accommodation": "\u5c0f\u5d0e\u6cca\u8cbb",
            "Dining & Drinks": "\u98df\u8cbb",
            "Transit": "\u4ea4\u901a\u8cbb",
            "Activities & Entry": "\u89b3\u5149\u30fb\u5165\u5834\u6599",
            "Miscellaneous": "\u96d1\u8cbb\u30fb\u304a\u571f\u7523\u4ee3",
            "Total": "\u5408\u8a08"
        },
        "saving_tips_title": "#### \U0001f4b8 \u7bc0\u7d04\u306e\u30b3\u30c4",
        "itinerary_title": "# \u2708\ufe0f \u5b8c\u5168\u65c5\u884c\u65e5\u7a0b: {destination}\u3067\u306e{duration}\u65e5\u9593",
        "day_label": "\U0001f4c5 {d}\u65e5\u76ee",
        "morning": "\u671d",
        "lunch": "\u663c\u98df",
        "afternoon": "\u5348\u5f8c",
        "evening": "\u591c",
        "checklist_title": "### \U0001f392 \u6700\u7d42\u65c5\u884c\u30c1\u30a7\u30c3\u30af\u30ea\u30b9\u30c8"
    },
    "French": {
        "research_title": "### \U0001f5fa\ufe0f R\u00e9sum\u00e9 de Recherche pour {destination}",
        "interests_label": "Adapt\u00e9 aux int\u00e9r\u00eats: {interests}",
        "attractions_title": "#### \U0001f31f Principales Attractions",
        "culinary_title": "#### \U0001f35c Points Forts Culinaires & Street Food",
        "tips_title": "#### \U0001f4a1 Conseils de Voyage Locaux",
        "budget_title": "### \U0001f4b0 Estimation du Budget pour {duration} Jours \u00e0 {destination}",
        "est_total": "- **Co\u00fbt Total Estim\u00e9**: {sym}{total} par personne",
        "limit_label": "- **Limite de Budget**: {sym}{limit}",
        "status_label": "- **Statut**: {status}",
        "within_budget": "Dans le budget",
        "exceeds_budget": "D\u00e9passe le budget",
        "table_headers": "| Cat\u00e9gorie | Co\u00fbt par Jour ({curr}) | Co\u00fbt Total ({curr}) | D\u00e9tails |",
        "categories": {
            "Accommodation": "H\u00e9bergement",
            "Dining & Drinks": "Restauration & Boissons",
            "Transit": "Transport",
            "Activities & Entry": "Activit\u00e9s & Entr\u00e9es",
            "Miscellaneous": "Divers",
            "Total": "Total"
        },
        "saving_tips_title": "#### \U0001f4b8 Conseils pour \u00c9conomiser",
        "itinerary_title": "# \u2708\ufe0f Itin\u00e9raire de Voyage Complet: {duration} Jours \u00e0 {destination}",
        "day_label": "\U0001f4c5 Jour {d}",
        "morning": "Matin",
        "lunch": "D\u00e9jeuner",
        "afternoon": "Apr\u00e8s-midi",
        "evening": "Soir\u00e9e",
        "checklist_title": "### \U0001f392 Liste de Contr\u00f4le Finale"
    },
    "German": {
        "research_title": "### \U0001f5fa\ufe0f Forschungsbericht f\u00fcr {destination}",
        "interests_label": "Abgestimmt auf Interessen: {interests}",
        "attractions_title": "#### \U0001f31f Hauptattraktionen",
        "culinary_title": "#### \U0001f35c Kulinarische Highlights & Street Food",
        "tips_title": "#### \U0001f4a1 Lokale Reisetipps",
        "budget_title": "### \U0001f4b0 Budgetsch\u00e4tzung f\u00fcr {duration} Tage in {destination}",
        "est_total": "- **Gesch\u00e4tzte Gesamtkosten**: {sym}{total} pro Person",
        "limit_label": "- **Budgetgrenze**: {sym}{limit}",
        "status_label": "- **Status**: {status}",
        "within_budget": "Im Budget",
        "exceeds_budget": "\u00dcber dem Budget",
        "table_headers": "| Kategorie | Kosten pro Tag ({curr}) | Gesamtkosten ({curr}) | Details |",
        "categories": {
            "Accommodation": "Unterkunft",
            "Dining & Drinks": "Verpflegung",
            "Transit": "Nahverkehr",
            "Activities & Entry": "Aktivit\u00e4ten & Eintritt",
            "Miscellaneous": "Sonstiges",
            "Total": "Gesamt"
        },
        "saving_tips_title": "#### \U0001f4b8 Budget-Spartipps",
        "itinerary_title": "# \u2708\ufe0f Vollst\u00e4ndige Reiseroute: {duration} Tage in {destination}",
        "day_label": "\U0001f4c5 Tag {d}",
        "morning": "Morgen",
        "lunch": "Mittagessen",
        "afternoon": "Nachmittag",
        "evening": "Abend",
        "checklist_title": "### \U0001f392 Finale Reise-Checkliste"
    },
    "Hindi": {
        "research_title": "### \U0001f5fa\ufe0f {destination} \u0915\u0947 \u0932\u093f\u090f \u0905\u0928\u0941\u0938\u0902\u0927\u093e\u0928 \u0938\u093e\u0930\u093e\u0902\u0936",
        "interests_label": "\u0930\u0941\u091a\u093f\u092f\u094b\u0902 \u0915\u0947 \u0905\u0928\u0941\u0938\u093e\u0930: {interests}",
        "attractions_title": "#### \U0001f31f \u092e\u0941\u0916\u094d\u092f \u0906\u0915\u0930\u094d\u0937\u0923",
        "culinary_title": "#### \U0001f35c \u0938\u094d\u0925\u093e\u0928\u0940\u092f \u0935\u094d\u092f\u0902\u091c\u0928 \u0914\u0930 \u0938\u094d\u091f\u094d\u0930\u0940\u091f \u092b\u0942\u0921",
        "tips_title": "#### \U0001f4a1 \u0938\u094d\u0925\u093e\u0928\u0940\u092f \u092f\u093e\u0924\u094d\u0930\u093e \u092f\u0941\u0915\u094d\u0924\u093f\u092f\u093e\u0902",
        "budget_title": "### \U0001f4b0 {destination} \u092e\u0947\u0902 {duration} \u0926\u093f\u0928\u094b\u0902 \u0915\u0947 \u0932\u093f\u090f \u092c\u091c\u091f \u0905\u0928\u0941\u092e\u093e\u0928",
        "est_total": "- **\u0905\u0928\u0941\u092e\u093e\u0928\u093f\u0924 \u0915\u0941\u0932 \u0932\u093e\u0917\u0924**: {sym}{total} \u092a\u094d\u0930\u0924\u093f \u0935\u094d\u092f\u0915\u094d\u0924\u093f",
        "limit_label": "- **\u092c\u091c\u091f \u0938\u0940\u092e\u093e**: {sym}{limit}",
        "status_label": "- **\u0938\u094d\u0925\u093f\u0924\u093f**: {status}",
        "within_budget": "\u092c\u091c\u091f \u0915\u0947 \u092d\u0940\u0924\u0930",
        "exceeds_budget": "\u092c\u091c\u091f \u0938\u0947 \u092c\u093e\u0939\u0930",
        "table_headers": "| \u0936\u094d\u0930\u0947\u0923\u0940 | \u092a\u094d\u0930\u0924\u093f \u0926\u093f\u0928 \u0932\u093e\u0917\u0924 ({curr}) | \u0915\u0941\u0932 \u0932\u093e\u0917\u0924 ({curr}) | \u0935\u093f\u0935\u0930\u0923 |",
        "categories": {
            "Accommodation": "\u0906\u0935\u093e\u0938 (\u0939\u094b\u091f\u0932)",
            "Dining & Drinks": "\u092d\u094b\u091c\u0928 \u0914\u0930 \u092a\u094d\u092f",
            "Transit": "\u092f\u093e\u0924\u093e\u092f\u093e\u0924",
            "Activities & Entry": "\u0917\u0924\u093f\u0935\u093f\u0927\u093f\u092f\u093e\u0902 \u0914\u0930 \u092a\u094d\u0930\u0935\u0947\u0936 \u0936\u0941\u0932\u094d\u0915",
            "Miscellaneous": "\u0935\u093f\u0935\u093f\u0927",
            "Total": "\u0915\u0941\u0932"
        },
        "saving_tips_title": "#### \U0001f4b8 \u092c\u091c\u091f \u092c\u091a\u0924 \u092f\u0941\u0915\u094d\u0924\u093f\u092f\u093e\u0902",
        "itinerary_title": "# \u2708\ufe0f \u092a\u0942\u0930\u094d\u0923 \u092f\u093e\u0924\u094d\u0930\u093e \u0915\u093e\u0930\u094d\u092f\u0915\u094d\u0930\u092e: {destination} \u092e\u0947\u0902 {duration} \u0926\u093f\u0928",
        "day_label": "\U0001f4c5 \u0926\u093f\u0928 {d}",
        "morning": "\u0938\u0941\u092c\u0939",
        "lunch": "\u0926\u094b\u092a\u0939\u0930 \u0915\u093e \u092d\u094b\u091c\u0928",
        "afternoon": "\u0926\u094b\u092a\u0939\u0930",
        "evening": "\u0936\u093e\u092e",
        "checklist_title": "### \U0001f392 \u0905\u0902\u0924\u093f\u092e \u092f\u093e\u0924\u094d\u0930\u093e \u091a\u0947\u0915\u0932\u093f\u0938\u094d\u091f"
    },
    "Telugu": {
        "research_title": "### \\U0001f5fa\\ufe0f {destination} \\u0c2a\\u0c30\\u0c3f\\u0c36\\u0c4b\\u0c27\\u0c28 \\u0c38\\u0c3e\\u0c30\\u0c3e\\u0c02\\u0c36\\u0c02",
        "interests_label": "\\u0c06\\u0c38\\u0c15\\u0c4d\\u0c24\\u0c41\\u0c32\\u0c15\\u0c41 \\u0c05\\u0c28\\u0c41\\u0c17\\u0c41\\u0c23\\u0c02\\u0c17\\ా: {interests}",
        "attractions_title": "#### \\u2b50\\ufe0f \\u0c2a\\u0c4d\\u0c30\\u0c27\\ా\\u0c28 \\u0c2a\\u0c30\\u0c4d\\u0c2f\\u0c3e\\u0c1f\\u0c15 \\u0c2a\\u0c4d\\u0c30\\u0c26\\u0c47\\u0c36\\ా\\u0c32\\ు",
        "culinary_title": "#### \\U0001f35c \\u0c38\\u0c4d\\u0c25\\u0c3e\\u0c28\\u0c3f\\u0c15 \\u0c35\\u0c02\\u0c1f\\u0c15\\ా\\u0c32\\u0c41 & \\u0c38\\u0c4d\\u0c1f\\u0c4d\\u0c30\\u0c40\\u0c1f\\u0c4d \\u0c2b\\u0c41\\u0c21\\u0c4d",
        "tips_title": "#### \\U0001f4a1 \\u0c38\\u0c4d\\u0c25\\u0c3e\\u0c28\\u0c3f\\u0c15 \\u0c2a\\u0c4d\\u0c30\\u0c2f\\u0c3e\\u0c23 \\u0c1a\\u0c3f\\u0c1f\\u0c4d\\u0c15\\ా\\u0c32\\u0c41",
        "budget_title": "### \\U0001f4b0 {destination} \\u0c32\\u0c4b {duration} \\u0c30\\u0c4b\\u0c1c\\u0c41\\u0c32 \\u0c2a\\u0c4d\\u0c30\\u0c2f\\u0c3e\\u0c23 \\u0c2c\\u0c21\\u0c4d\\u0c1c\\u0c46\\u0c1f\\u0c4d \\u0c05\\u0c02\\u0c1a\\u0c28\\ా",
        "est_total": "- **\\u0c05\\u0c02\\u0c1a\\u0c28\\u0c3e \\u0c35\\u0c47\\u0c38\\u0c3f\\u0c28 \\u0c2e\\u0c4a\\u0c24\\u0c4d\\u0c24\\u0c02 \\u0c16\\u0c30\\u0c4d\\u0c1a\\u0c41**: \\u0c12\\u0c15\\u0c4d\\u0c15\\u0c4a\\u0c15\\u0c4d\\u0c15\\u0c30\\u0c3f\\క\\ట {sym}{total}",
        "limit_label": "- **\\u0c2c\\u0c21\\u0c4d\\u0c1c\\u0c46\\u0c1f\\u0c4d \\u0c2a\\u0c30\\u0c3f\\u0c2e\\u0c3f\\u0c24\\u0c3f**: {sym}{limit}",
        "status_label": "- **\\u0c38\\u0c4d\\u0c25\\u0c3f\\u0c24\\u0c3f**: {status}",
        "within_budget": "\\u0c2c\\u0c21\\u0c4d\\u0c1c\\u0c46\\u0c1f\\u0c4d \\u0c2a\\u0c30\\u0c3f\\u0c27\\u0c3f\\u0c32\\u0c4b",
        "exceeds_budget": "\\u0c2c\\u0c21\\u0c4d\\u0c1c\\u0c46\\u0c1f\\u0c4d \\u0c2e\\u0c3f\\u0c02\\u0c1a\\u0c3f\\u0c2a\\u0c4b\\u0c2f\\u0c3f\\u0c02\\u0c26\\u0c3f",
        "table_headers": "| \\u0c35\\u0c30\\u0c4d\\u0c17\\u0c02 | \\u0c30\\u0c4b\\u0c1c\\u0c41\\u0c35\\u0c3e\\u0c30\\u0c40 \\u0c16\\u0c30\\u0c4d\\u0c1a\\u0c41 ({curr}) | \\u0c2e\\u0c4a\\u0c24\\u0c4d\\u0c24\\u0c02 \\u0c16\\u0c30\\u0c4d\\u0c1a\\u0c41 ({curr}) | \\u0c35\\u0c3f\\u0c35\\u0c30\\u0c3e\\u0c32\\u0c41 |",
        "categories": {
            "Accommodation": "\\u0c35\\u0c38\\u0c24\\u0c3f (\\u0c39\\u0c4b\\u0c1f\\u0c32)",
            "Dining & Drinks": "\\u0c2d\\u0c4b\\u0c1c\\u0c28\\u0c02 & \\u0c2a\\u0c3e\\u0c28\\ీ\\u0c2f\\u0c3e\\u0c32\\u0c41",
            "Transit": "\\u0c30\\u0c35\\u0c3e\\u0c23\\u0c3e",
            "Activities & Entry": "\\u0c15\\u0c3e\\u0c30\\u0c4d\\u0c2f\\u0c15\\u0c3e\\u0c32\\u0c3e\\u0c32\\u0c41 & \\u0c2a\\u0c4d\\u0c30\\u0c35\\u0c47\\u0c36 \\u0c30\\u0c41\\u0c35\\ు\\మ\\u0c41",
            "Miscellaneous": "\\u0c07\\u0c24\\u0c30 \\u0c16\\u0c30\\u0c4d\\u0c1a\\u0c41\\u0c32\\u0c41",
            "Total": "\\u0c2e\\u0c4a\\u0c24\\u0c4d\\u0c24\\u0c02"
        },
        "saving_tips_title": "#### \\u0c2c\\u0c21\\u0c4d\\u0c1c\\u0c46\\u0c1f\\u0c4d \\u0c06\\u0c26\\u0c3e \\u0c1a\\u0c3f\\ట\\u0c4d\\u0c15\\u0c3e\\u0c32\\u0c41",
        "itinerary_title": "# \\u2708\\ufe0f \\u0c2a\\u0c4d\\u0c30\\u0c2f\\u0c3e\\u0c23 \\u0c2a\\u0c4d\\u0c30\\u0c23\\u0c3e\\u0c32\\u0c3f\\u0c15: {destination} \\u0c32\\u0c4b {duration} \\u0c30\\u0c4b\\u0c1c\\u0c41\\u0c32\\u0c41",
        "day_label": "\\ud83d\\udcc5 {d}\\u0c35 \\u0c30\\u0c4b\\u0c1c\\u0c41",
        "morning": "\\u0c09\\u0c26\\u0c2f\\u0c02",
        "lunch": "\\u0c2e\\u0c27\\u0c4d\\u0c2f\\u0c3e\\u0c39\\u0c4d\\u0c28 \\u0c2d\\u0c4b\\u0c1c\\u0c28\\u0c02",
        "afternoon": "\\u0c2e\\u0c27\\u0c4d\\u0c2f\\u0c3e\\u0c39\\u0c4d\\u0c28\\u0c02",
        "evening": "\\u0c38\\ా\\u0c2f\\u0c02\\u0c24\\u0c4d\\u0c30\\u0c02",
        "checklist_title": "### \\u0c2a\\u0c4d\\u0c30\\u0c2f\\u0c3e\\u0c23 \\u0c1a\\u0c46\\u0c15\\u0c4d\\u0c32\\u0c3f\\u0c38\\u0c4d\\u0c1f\\u0c4d"
    },
}

# Pre-localized details for Kyoto to create immersive experiences
kyoto_localizations = {
    "Spanish": {
        "attractions": "1. **Santuario Fushimi Inari**: Famoso por sus miles de puertas torii rojas que suben la monta\u00f1a.\n2. **Kinkaku-ji (Pabell\u00f3n Dorado)**: Un impresionante templo Zen cubierto de pan de oro.\n3. **Bosque de Bamb\u00fa de Arashiyama**: Senderos serenos rodeados de tallos de bamb\u00fa gigantes.\n4. **Kiyomizu-dera**: Un templo de madera hist\u00f3rico con vistas panor\u00e1micas de la ciudad.",
        "culinary": "- **Mercado Nishiki**: Una calle comercial estrecha de 400 a\u00f1os de antig\u00fcedad repleta de puestos de comida.\n- **Matcha en Gion**: Postres aut\u00e9nticos de matcha Uji en el distrito hist\u00f3rico.\n- **Kyoto Ramen**: Ramen tradicional de estilo Shoyu o Tonkotsu rico.",
        "tips": "- **Control de multitudes**: Visite Fushimi Inari y Arashiyama al amanecer (alrededor de las 6:30 AM).\n- **Tr\u00e1nsito**: Compre una tarjeta IC ICOCA para viajes en autob\u00fas y metro.\n- **Cultura**: Respete a las Geishas en Gion; no tome fotos sin permiso.",
        "saving_tips": "- Obtenga el Pase de 1 D\u00eda para Metro y Autob\u00fas de Kioto.\n- Compre deliciosos desayunos econ\u00f3micos como Onigiri en FamilyMart o Lawson.\n- \u00a1Muchos santuarios (como Yasaka y Fushimi Inari) son completamente gratuitos!",
        "itinerary_day1": "- **Ma\u00f1ana (07:00 - 11:30)**: Evite las multitudes en **Santuario Fushimi Inari**.\n- **Almuerzo (12:00 - 13:30)**: Deguste especialidades en **Mercado Nishiki**.\n- **Tarde (14:00 - 17:00)**: Visite el **Kinkaku-ji (Pabell\u00f3n Dorado)**.\n- **Noche (18:00 - 20:30)**: Explore las calles hist\u00f3ricas de **Gion**.",
        "itinerary_day2": "- **Ma\u00f1ana (07:30 - 11:00)**: Pasee temprano por el **Bosque de Bamb\u00fa de Arashiyama**.\n- **Almuerzo (11:30 - 13:00)**: Disfrute de una comida tradicional de tofu (Yudofu).\n- **Tarde (13:30 - 16:30)**: Cruce el puente Togetsukyo y visite el Parque de Monos.\n- **Noche (17:30 - 20:30)**: Camine por el pintoresco callej\u00f3n **Pontocho**.",
        "itinerary_day3": "- **Ma\u00f1ana (08:30 - 11:30)**: Visite el templo **Kiyomizu-dera**.\n- **Almuerzo (12:00 - 13:30)**: Almuerce en un restaurante tradicional de Soba.\n- **Tarde (13:30 - 16:30)**: Camine por las calles preservadas de **Sannenzaka y Ninenzaka**.\n- **Noche (17:30 - 20:00)**: Disfrute del atardecer en el **Santuario Yasaka**.",
        "checklist": "- [x] Comprar el pase de metro y autob\u00fas de 1 d\u00eda.\n- [ ] Reservar la ceremonia del t\u00e9 en Arashiyama.\n- [x] Imprimir o guardar la reserva del Ryokan.\n- [ ] Llevar calzado c\u00f3modo para caminar."
    },
    "Japanese": {
        "attractions": "1. **\u4f0f\u898b\u7a32\u8377\u5927\u793e**: \u5c71\u9802\u306b\u5411\u304b\u3063\u3066\u5343\u672c\u9df4\u9ce5\u5c45\u304c\u4e16\u754c\u7684\u306b\u6709\u540d\u306a\u795e\u793e\u3002\n2. **\u91d1\u95a3\u5bfa (\u9e7a\u82d1\u5bfa)**: \u93e1\u6e56\u6c60\u306b\u6620\u3057\u8fbc\u3080\u3001\u91d1\u7b94\u3067\u8986\u308f\u308c\u305f\u7f8e\u3057\u3044\u7985\u5bfa\u3002\n3. **\u5d50\u5c71\u306e\u7af9\u6797\u306e\u5c0f\u5f91**: \u5929\u9ad8\u304f\u4f38\u3073\u308b\u7af9\u6797\u306b\u56f2\u308f\u308c\u305f\u3001\u98a8\u60c5\u3042\u308b\u6563\u7b56\u8def\u3002\n4. **\u6e05\u6c34\u5bfa**: \u672c\u5802\u306e\u821e\u53f0\u304b\u3089\u4eac\u90fd\u306e\u8857\u4e26\u307f\u3092\u4e00\u671b\u3067\u304d\u308b\u6b74\u53f2\u3042\u308b\u5bfa\u9662\u3002",
        "culinary": "- **\u9326\u5e02\u5834**: \u300c\u4eac\u90fd\u306e\u53f0\u6240\u300d\u3068\u547c\u3070\u308c\u308b400\u5e74\u306e\u6b74\u53f2\u3092\u6301\u3064\u5546\u5e97\u8857\u3002\n- **\u821e\u95a3\u306e\u62b9\u8336\u30d1\u30d5\u30a7**: \u6b74\u53f2\u3042\u308b\u82b1\u8857\u3067\u5473\u308f\u3046\u672c\u5834\u30fb\u5b87\u6cbb\u62b9\u8336\u3092\u4f7f\u7528\u3057\u305f\u30b9\u30a4\u30fc\u30c4\u3002\n- **\u4eac\u90fd\u30e9\u30fc\u30e1\u30f3**: \u4eac\u90fd\u30a8\u30f3\u30b8\u30f3\u30e9\u30fc\u30e1\u30f3\u306a\u3069\u3067\u63d0\u4f9b\u3055\u308c\u308b\u3001\u6fc3\u539a\u306a\u91dd\u91c9\u30fb\u3068\u3093\u3053\u3064\u30e9\u30fc\u30e1\u30f3\u3002",
        "tips": "- **\u6df7\u96d1\u56de\u907f**: \u4f0f\u898b\u7a32\u8377\u3084\u5d50\u5c71\u306f\u65e9\u671d\uff08\u5348\u524d6\u6642\u534a\u9803\uff09\u306e\u89b3\u5149\u304c\u6700\u3082\u9759\u304b\u3067\u5feb\u9069\u3067\u3059\u3002\n- **\u4ea4\u901a\u624b\u6bb5**: \u30d0\u30b9\u3084\u5730\u4e0b\u9245\u306e\u79fb\u52d5\u306b\u306f\u4ea4\u901a\u7cfbIC\u30ab\u30fc\u30c9\uff08ICOCA\u306a\u3069\uff09\u304c\u975e\u5e38\u306b\u4fbf\u5229\u3067\u3059\u3002\n- **\u30de\u30ca\u30fc**: \u821e\u95a3\u306e\u79c1\u9053\u3067\u306e\u64ae\u5f71\u7981\u6b62\u30eb\u30fc\u30eb\u3092\u9805\u5b88\u3057\uff0c\u82b8\u4f03\u30fb\u821e\u4f03\u3055\u3092\u8ffd\u3044\u304b\u3051\u306a\u3044\u3067\u304f\u3060\u3055\u3044\u3002",
        "saving_tips": "- \u5730\u4e0b\u9245\u30fb\u30d0\u30b9\u4e00\u65e5\u4e57\u8eca\u5235\u306e\u8cfc\u5165\u304c\u304a\u5f97\u3067\u3059\u3002\n- \u671d\u98df\u306f\u30b3\u30f3\u30d3\u30cb\uff08\u30d5\u30a1\u30df\u30ea\u30fc\u30de\u30fc\u30c8\u3084\u30ed\u30fc\u30bd\u30f3\uff09\u306e\u304a\u306b\u304e\u308a\u7b49\u3067\u7bc0\u7d04\u3067\u304d\u307e\u3059\u3002\n- \u4f0f\u898b\u7a32\u8377\u5927\u793e\u3084\u516b\u5742\u795e\u793e\u306a\u3069\uff0c\u591a\u304f\u306e\u4e3b\u306a\u795e\u793e\u306f\u53c2\u62dd\u6599\u304c\u300c\u7121\u6599\u300d\u3067\u3059\u3002",
        "itinerary_day1": "- **\u5348\u524d (07:00 - 11:30)**: \u6df7\u96d1\u3092\u907f\u3051\u3066**\u4f0f\u898b\u7a32\u8377\u5927\u793e**\u3092\u30cf\u30a4\u30ad\u30f3\u30b0\u3002\n- **\u663c\u98df (12:00 - 13:30)**: **\u9326\u5e02\u5834**\u3067\u4e32\u89bc\u304d\u3084\u3060\u3057\u5dfb\u304d\u5375\u3092\u98df\u3079\u6b69\u304d\u3002\n- **\u5348\u5f8c (14:00 - 17:00)**: \u9ec4\u91d1\u306b\u8f1d\u304f**\u91d1\u95a3\u5bfa**\u3092\u53c2\u62dd\u3002\n- **\u5915\u65b9\u30fb\u591c (18:00 - 20:30)**: \u6b74\u53f2\u3042\u308b**\u821e\u95a3**\u3092\u6563\u7b56\u3057\uff0c\u30e9\u30fc\u30e1\u30f3\u3092\u582a\u80fd\u3002",
        "itinerary_day2": "- **\u5348\u524d (07:30 - 11:00)**: \u65e9\u671d\u306e\u9759\u304b\u306a**\u5d50\u5c71\u7af9\u6797\u306e\u5c0f\u5f91**\u3092\u6563\u6b69\u3057\uff0c\u5929\u9fe1\u5bfa\u3078\u3002\n- **\u663c\u98df (11:30 - 13:00)**: \u5927\u5830\u5ddd\u3092\u773a\u3081\u306a\u304c\u3089\u4f1d\u7d71\u7684\u306a\u6e6f\u8c46\u8150\u3092\u582a\u80fd\u3002\n- **\u5348\u5f8c (13:30 - 16:30)**: \u6e21\u6708\u6a4b\u3092\u6e21\u308a\u30e2\u30f3\u30ad\u30fc\u30d1\u30fc\u30af\u3092\u8a2a\u554f\u3001\u62b9\u8336\u8336\u9053\u3092\u4f53\u9a13\u3002\n- **\u5915\u65b9\u30fb\u591c (17:30 - 20:30)**: \u30e9\u30f3\u30bf\u30f3\u304c\u706f\u308b\u60c5\u7dd2\u3042\u308b**\u5148\u6597\u753a**\u3067\u5c45\u9152\u5c4b\u30c7\u30a3\u30ca\u30fc\u3002",
        "itinerary_day3": "- **\u5348\u524d (08:30 - 11:30)**: \u4eac\u90fd\u306e\u8857\u3092\u898b\u6e21\u305b\u308b\u4f1d\u7d71\u306e\u821e\u53f0\u3001**\u6e05\u6c34\u5bfa**\u3078\u3002\n- **\u663c\u98df (12:00 - 13:30)**: \u6771\u5c71\u30a8\u30ea\u30a2\u306e\u98a8\u60c5\u3042\u308b\u854a\u9ea6\u5c4b\u3067\u663c\u98df\u3002\n- **\u5348\u5f8c (13:30 - 16:30)**: **\u4e09\u5e74\u5742\u30fb\u4e8c\u5e74\u5742**\u3092\u6563\u7b56\u3057\uff0c\u304a\u571f\u7523\u8cfc\u5165\u3084\u62b9\u8336\u3082\u3061\u3092\u8a66\u98df\u3002\n- **\u5915\u65b9\u30fb\u591c (17:30 - 20:00)**: \u5915\u66ae\u308c\u6642\u306e**\u516b\u5742\u795e\u793e**\u306b\u53c2\u62dd\u3057\uff0c\u9d28\u5ddd\u6cbf\u3044\u3067\u30c7\u30a3\u30ca\u30fc\u3002",
        "checklist": "- [x] \u30d0\u30b9\u30fb\u5730\u4e0b\u9245\u4e00\u65e5\u4e57\u8eca\u5235\u3092\u8cfc\u5165\u3059\u308b\u3002\n- [ ] \u5d50\u5c71\u306e\u8336\u9053\u4f53\u9a13\u3092\u4e88\u7d04\u3059\u308b\u3002\n- [x] \u65c5\u9928\u306e\u4e88\u7d04\u78ba\u8a8d\u66f8\u3092\u4fdd\u5b58\u3059\u308b\u3002\n- [ ] \u6b69\u304d\u3084\u3059\u3044\u9774\u3092\u7528\u610f\u3059\u308b\uff081\u65e51\u4e075\u5343\u6b69\u4ee5\u4e0a\u6b69\u304d\u307e\u3059\uff09\u3002"
    },
    "French": {
        "attractions": "1. **Sanctuaire Fushimi Inari**: C\u00e9l\u00e8bre pour ses milliers de portails torii rouges grimpant la montagne.\n2. **Kinkaku-ji (Pavillon d'Or)**: Un temple Zen recouvert de feuilles d'or, refl\u00e9t\u00e9 sur l'\u00e9tang.\n3. **Bambouseraie d'Arashiyama**: Des sentiers paisibles au milieu de bambous g\u00e9ants.\n4. **Kiyomizu-dera**: Un temple historique en bois offrant des vues panoramiques sur Kyoto.",
        "culinary": "- **March\u00e9 Nishiki**: Une rue commer\u00e7ante \u00e9troite vieille de 400 ans, remplie de stands.\n- **Matcha \u00e0 Gion**: Desserts authentiques au th\u00e9 matcha d'Uji dans le quartier de Gion.\n- **Ramen de Kyoto**: Ramen riche de style Tonkotsu ou Shoyu local.",
        "tips": "- **\u00c9viter la foule**: Visitez Fushimi Inari et Arashiyama au lever du soleil (vers 6h30).\n- **Transport**: Utilisez une carte IC ICOCA pour un voyage fluide en bus et en m\u00e9tro.\n- **Culture**: Respectez les Geishas \u00e0 Gion et ne prenez pas de photos sans autorisation.",
        "saving_tips": "- Prenez le pass de transport 1 jour de m\u00e9tro & bus de Kyoto.\n- Achetez des en-cas abordables comme des Onigiri dans les sup\u00e9rettes (konbini).\n- De nombreux sanctuaires (Fushimi Inari, Yasaka) sont enti\u00e8rement gratuits !",
        "itinerary_day1": "- **Matin (07:00 - 11:30)**: \u00c9vitez la foule au **Sanctuaire Fushimi Inari**.\n- **D\u00e9jeuner (12:00 - 13:30)**: D\u00e9gustez des sp\u00e9cialit\u00e9s au **March\u00e9 Nishiki**.\n- **Après-midi (14:00 - 17:00)**: Visitez le majestueux **Kinkaku-ji**.\n- **Soir\u00e9e (18:00 - 20:30)**: Explorez les ruelles de **Gion** et d\u00eener.",
        "itinerary_day2": "- **Matin (07:30 - 11:00)**: Profitez de la **Bambouseraie d'Arashiyama** et du Tenryu-ji.\n- **D\u00e9jeuner (11:30 - 13:00)**: Savourez un repas traditionnel de tofu (Yudofu).\n- **Après-midi (13:30 - 16:30)**: Visitez le parc des singes et assistez \u00e0 une c\u00e9r\u00e9monie du th\u00e9.\n- **Soir\u00e9e (17:30 - 20:30)**: Promenez-vous dans la pittoresque **All\u00e9e Pontocho**.",
        "itinerary_day3": "- **Matin (08:30 - 11:30)**: Admirez la vue depuis la terrasse du temple **Kiyomizu-dera**.\n- **D\u00e9jeuner (12:00 - 13:30)**: D\u00e9gustez des nouilles Soba \u00e0 Higashiyama.\n- **Après-midi (13:30 - 16:30)**: Explorez les rues pi\u00e9tonnes de **Sannenzaka et Ninenzaka**.\n- **Soir\u00e9e (17:30 - 20:00)**: Admirez le coucher du soleil au **Sanctuaire Yasaka**.",
        "checklist": "- [x] Acheter le pass m\u00e9tro & bus 1 jour.\n- [ ] R\u00e9server la c\u00e9r\u00e9monie du th\u00e9 \u00e0 Arashiyama.\n- [x] Sauvegarder les d\u00e9tails de r\u00e9servation du Ryokan.\n- [ ] Apporter des chaussures de marche confortables."
    },
    "German": {
        "attractions": "1. **Fushimi Inari-Schrein**: Ber\u00fchmt f\u00fcr seine Pfade aus 10.000 roten Torii-Toren den Berg hinauf.\n2. **Kinkaku-ji (Goldener Pavillon)**: Ein atemberaubender, mit Blattgold bedeckter Zen-Tempel.\n3. **Arashiyama Bambuswald**: Riesige Bambusst\u00e4ngel, die eine beruhigende Atmosphäre schaffen.\n4. **Kiyomizu-dera**: Ein historischer Holztempel mit Panoramablick \u00fcber die Stadt.",
        "culinary": "- **Nishiki-Markt**: Eine 400 Jahre alte, schmale Einkaufsstra\u00dfe mit \u00fcber hundert St\u00e4nden.\n- **Matcha in Gion**: Authentische Matcha-Desserts im historischen Stadtteil Gion.\n- **Kyoto Ramen**: Herzhaftes Ramen im Tonkotsu- oder Shoyu-Stil bei lokalen H\u00e4ndlern.",
        "tips": "- **Massen meiden**: Besuchen Sie Fushimi Inari und Arashiyama bei Sonnenaufgang (ca. 06:30 Uhr).\n- **Nahverkehr**: Nutzen Sie eine ICOCA-Karte f\u00fcr bequeme Fahrten in Bus und U-Bahn.\n- **Kultur**: Respektieren Sie Geishas in Gion; Fotografieren ist teils streng verboten.",
        "saving_tips": "- Kaufen Sie das Kyoto 1-Tages-Ticket f\u00fcr U-Bahn und Bus.\n- Fr\u00fchst\u00fccken Sie preiswert mit Onigiri aus dem FamilyMart oder Lawson.\n- Viele Schreine (wie Fushimi Inari und Yasaka) kosten keinen Eintritt!",
        "itinerary_day1": "- **Morgen (07:00 - 11:30)**: Fr\u00fchmorgens zum **Fushimi Inari-Schrein** wandern.\n- **Mittagessen (12:00 - 13:30)**: Street Food auf dem **Nishiki-Markt** probieren.\n- **Nachmittag (14:00 - 17:00)**: Den goldenen **Kinkaku-ji** Tempel bestaunen.\n- **Abend (18:00 - 20:30)**: Spaziergang durch die alten Gassen von **Gion**.",
        "itinerary_day2": "- **Morgen (07:30 - 11:00)**: Den **Arashiyama Bambuswald** und Tenryu-ji Tempel erkunden.\n- **Mittagessen (11:30 - 13:00)**: Traditionelles Tofu-Gericht (Yudofu) genie\u00dfen.\n- **Nachmittag (13:30 - 16:30)**: Besuch des Affenparks und Teilnahme an einer Teezeremonie.\n- **Abend (17:30 - 20:30)**: Abendessen in der beleuchteten **Pontocho-Gasse**.",
        "itinerary_day3": "- **Morgen (08:30 - 11:30)**: Panoramablick vom Tempel **Kiyomizu-dera** genie\u00dfen.\n- **Mittagessen (12:00 - 13:30)**: Soba-Nudeln in der historischen Altstadt essen.\n- **Nachmittag (13:30 - 16:30)**: Schlendern durch die Gassen **Sannenzaka und Ninenzaka**.\n- **Abend (17:30 - 20:00)**: Sonnenuntergang am **Yasaka-Schrein** betrachten.",
        "checklist": "- [x] Das 1-Tages-Ticket f\u00fcr Bus und U-Bahn kaufen.\n- [ ] Die Teezeremonie in Arashiyama im Voraus buchen.\n- [x] Ryokan-Reservierung auf dem Handy speichern.\n- [ ] Bequeme Laufschuhe einpacken."
    },
    "Hindi": {
        "attractions": "1. **\u092b\u0941\u0936\u093f\u092e\u0940 \u0905\u0928\u094d\u0928\u093e\u0930\u0940 \u0936\u094d\u0930\u093e\u0907\u0928**: \u092a\u0939\u093e\u0921\u093c \u092a\u0930 \u091a\u0922\u093c\u0924\u0947 \u0939\u0941\u090f \u0967\u0968,\u0966\u0966\u0966 \u0932\u093e\u0932 \u0924\u094b\u0930\u0940 \u0926\u094d\u0935\u093e\u0930\u094b\u0902 \u0915\u093e \u092a\u094d\u0930\u0935\u0947\u0936 \u092e\u093e\u0930\u094d\u0917\u0964\n2. **\u0915\u093f\u0902\u0915\u093e\u0915\u0941-\u091c\u0940**: \u0938\u094b\u0928\u0947 \u0915\u0940 \u092a\u0930\u0924 \u0938\u0947 \u0922\u0915\u093e \u090f\u0915 \u0936\u093e\u0928\u0926\u093e\u0930 \u091c\u093c\u0947\u0928 \u092e\u0902\u0926\u093f\u0930\u0964\n3. **\u0906\u0930\u093e\u0936\u093f\u092f\u092e\u093e \u092c\u093e\u0902\u0938 \u0915\u093e \u091c\u0902\u0917\u0932**: \u092c\u093e\u0902\u0938 \u0915\u0947 \u0935\u093f\u0936\u093e\u0932 \u0924\u0928\u094b\u0902 \u0915\u0947 \u092c\u0940\u091a \u090f\u0915 \u0936\u093e\u0902\u0924 \u092e\u093e\u0930\u094d\u0917\u0964\n4. **\u0915\u093f\u092f\u094b\u092e\u093f\u091c\u093c\u0942-\u0921\u0947\u0930\u093e**: \u0936\u0939\u0930 \u0915\u0947 \u092e\u0928\u094b\u0930\u092e \u0926\u0943\u0936\u094d\u092f \u092a\u094d\u0930\u0938\u094d\u0924\u0941\u0924 \u0915\u0930\u0928\u0947 \u0935\u093e\u0932\u093e \u090f\u0915 \u0910\u0924\u093f\u0939\u093e\u0938\u093f\u0915 \u0932\u0915\u0921\u093c\u0940 \u0915\u093e \u092e\u0902\u0926\u093f\u0930\u0964",
        "culinary": "- **\u0928\u093f\u0936\u093f\u0915\u0940 \u092e\u093e\u0930\u094d\u0915\u0947\u091f**: \u0916\u093e\u0926\u094d\u092f \u092a\u0926\u093e\u0930\u094d\u0925\u094b\u0902 \u0915\u0940 \u0926\u0941\u0915\u093e\u0928\u094b\u0902 \u0938\u0947 \u092d\u0930\u0940 \u096a\u0966\u0966 \u0938\u093e\u0932 \u092a\u0941\u0930\u093e\u0928\u0940 \u0938\u0902\u0915\u0930\u0940 \u0938\u0921\u093c\u0915\u0964\n- **\u0917\u093f\u092f\u0949\u0928 \u092e\u0947\u0902 \u092e\u093e\u091a\u093e**: \u0910\u0924\u093f\u0939\u093e\u0938\u093f\u0915 \u0917\u093f\u092f\u0949\u0928 \u091c\u093f\u0932\u0947 \u092e\u0947\u0902 \u092a\u094d\u0930\u093e\u092e\u093e\u0923\u093f\u0915 \u0909\u091c\u0940 \u092e\u093e\u091a\u093e (Matcha) \u0921\u0947\u0938\u0930\u094d\u091f\u0964\n- **\u0915\u094d\u092f\u094b\u091f\u094b \u0930\u093e\u092e\u0947\u0928**: \u0938\u094d\u0925\u093e\u0928\u0940\u092f \u0926\u0941\u0915\u093e\u0928\u094b\u0902 \u092a\u0930 \u092e\u093f\u0932\u0928\u0947 \u0935\u093e\u0932\u093e \u0938\u0935\u093e\u0926\u093f\u0937\u094d\u091f \u0914\u0930 \u0917\u0930\u094d\u092e\u093e-\u0917\u0930\u094d\u092e \u0930\u093e\u092e\u0947\u0928 (Ramen)\u0964",
        "tips": "- **\u092d\u0940\u0921\u093c \u0938\u094d\u0925\u093f\u0924\u093f**: \u0936\u093e\u0902\u0924 \u0905\u0928\u0941\u092d\u0935 \u0915\u0947 \u0932\u093f\u090f \u0938\u0942\u0930\u094d\u092f\u094b\u0926\u092f (\u0938\u0941\u092c\u0939 \u09ec:\u0969\u0966 \u092c\u091c\u0947) \u0915\u0947 \u0906\u0938\u092a\u093e\u0938 \u092b\u0941\u0936\u093f\u092e\u0940 \u091c\u093e\u090f\u0902\u0964\n- **\u092f\u093e\u0924\u093e\u092f\u0924**: \u0906\u0938\u093e\u0928 \u092f\u093e\u0924\u094d\u0930\u093e \u0915\u0947 \u0932\u093f\u090f \u0906\u0908\u0938\u0940\u0913\u0938\u0940\u090f \u0915\u093e\u0930\u094d\u0921 (ICOCA) \u0916\u0930\u0940\u0926\u0947\u0902\u0964\n- **\u0936\u093f\u0937\u094d\u091f\u093e\u091a\u093e\u0930**: \u0917\u093f\u092f\u0949\u0928 \u0915\u0940 \u0938\u0921\u093c\u0915\u094b\u0902 \u092a\u0930 \u092e\u0930\u094d\u092f\u093e\u0926\u093e \u0930\u0916\u0947\u0902 \u0914\u0930 \u092c\u093f\u0928\u093e \u0905\u0928\u0941\u092e\u0924\u093f \u0924\u0938\u094d\u0935\u0940\u0930\u0947\u0902 \u0928 \u0932\u0947\u0902\u0964",
        "saving_tips": "- \u0915\u094d\u092f\u094b\u091f\u094b \u092c\u0938 \u0914\u0930 \u0938\u092c\u0935\u0947 \u096b-\u0926\u093f\u0935\u0938\u0940\u092f \u092a\u093e\u0938 \u0915\u094d\u0930\u094d\u092f \u0915\u0930\u0947\u0902\u0964\n- \u092b\u0942\u0921 \u092e\u093e\u0930\u094d\u0915\u0947\u091f \u092f\u093e \u0915\u0928\u094d\u0935\u0940\u0928\u093f\u092f\u0902\u0938 \u0938\u094d\u091f\u094b\u0930 \u0938\u0947 \u0938\u0938\u094d\u0924\u093e \u0928\u093e\u0936\u094d\u0924\u093e \u0932\u0947\u0902\u0964\n- \u092b\u0941\u0936\u093f\u092e\u0940 \u0905\u0928\u094d\u0928\u093e\u0930\u0940 \u0914\u0930 \u092f\u093e\u0938\u093e\u0915\u093e \u093e\u094d\u0930\u093e\u0901\u0907\u0928 \u0915\u093f\u0938\u0940 \u092a\u093e\u0938 \u092a\u094d\u0930\u0935\u0947\u0936 \u0936\u0941\u0932\u094d\u0915 \u0915\u0947 \u092c\u093f\u0928\u093e \u0918\u0942\u092e \u0938\u0915\u0924\u0947 \u0939\u0948\u0902!",
        "itinerary_day1": "- **\u0938\u0941\u092c\u0939 (07:00 - 11:30)**: \u092d\u0940\u0921\u093c \u0935\u094d\u092f\u0935\u0938\u094d\u0925\u093e \u0938\u0945 \u092c\u091a\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u091c\u0932\u094d\u0926\u0940 **\u092b\u0941\u0936\u093f\u092e\u0940 \u0905\u0928\u094d\u0928\u093e\u0930\u0940 \u0936\u094d\u0930\u093e\u0907\u0928** \u0915\u0940 \u092f\u093e\u0924\u094d\u0930\u093e \u0915\u0930\u0947\u0902\u0964\n- **\u0926\u094b\u092a\u0939\u0930 \u0915\u093e \u092d\u094b\u091c\u0928 (12:00 - 13:30)**: **\u0928\u093f\u0936\u093f\u0915\u0940 \u092e\u093e\u0930\u094d\u0915\u0947\u091f** \u092e\u0947\u0902 \u0916\u093e\u0926\u094d\u092f \u092a\u0926\u093e\u0930\u094d\u0925\u094b\u0902 \u0915\u093e \u0938\u094d\u0935\u093e\u0926 \u0932\u0947\u0902\u0964\n- **\u0926\u094b\u092a\u0939\u0930 (14:00 - 17:00)**: \u0938\u094d\u0935\u0930\u094d\u0923 \u092e\u0902\u0926\u093f\u0930 **\u0915\u093f\u0902\u0915\u093e\u0915\u0941-\u091c\u0940** \u0915\u093e \u092d\u094d\u0930\u092e\u0923 \u0915\u0930\u0947\u0902\u0964\n- **\u0936\u093e\u092e (18:00 - 20:30)**: **\u0917\u093f\u092f\u0949\u0928** \u0915\u0940 \u0917\u0932\u093f\u092f\u094b\u0902 \u092e\u0947\u0902 \u0918\u0942\u092e\u0947\u0902 \u0914\u0930 \u0930\u093e\u092e\u0947\u0928 \u0915\u093e \u0905\u0928\u0941\u092d\u0935 \u0932\u0947\u0902\u0964",
        "itinerary_day2": "- **\u0938\u0941\u092c\u0939 (07:30 - 11:00)**: **\u0906\u0930\u093e\u0936\u093f\u092f\u092e\u093e \u092c\u093e\u0902\u0938 \u0915\u0947 \u091c\u0902\u0917\u0932** \u0915\u093e \u0936\u093e\u0902\u0924 \u0926\u094c\u0930\u093e \u0915\u0930\u0947\u0902\u0964\n- **\u0926\u094b\u092a\u0939\u0930 \u0915\u093e \u092d\u094b\u091c\u0928 (11:30 - 13:00)**: \u092e\u0928\u094b\u0930\u092e \u0928\u0926\u0940 \u0915\u093f\u0928\u093e\u0930\u0947 \u092a\u093e\u0930\u0902\u092a\u0930\u093f\u0915 \u091f\u094b\u092f\u0942 \u0916\u093e\u090f\u0902\u0964\n- **\u0926\u094b\u092a\u0939\u0930 (13:30 - 16:30)**: \u092e\u0902\u0915\u0940 \u092a\u093e\u0930\u094d\u0915 \u0915\u093e \u092d\u094d\u0930\u092e\u0923 \u0915\u0930\u0947\u0902 \u0914\u0930 \u091a\u093e\u092f \u0938\u092e\u093e\u0930\u094b\u0939 \u0926\u0947\u0916\u0947\u0902\u0964\n- **\u0936\u093e\u092e (17:30 - 20:30)**: **\u092a\u094b\u0902\u091f\u094b\u091a\u094b \u0917\u0932\u0940** \u092e\u0947\u0902 \u091f\u0939\u0932\u0947\u0902 \u0914\u0930 \u0907\u091c\u093e\u0915\u093e\u092f\u093e \u092e\u0947\u0902 \u0921\u093f\u0928\u0930 \u0915\u0930\u0947\u0902\u0964",
        "itinerary_day3": "- **\u0938\u0941\u092c\u0939 (08:30 - 11:30)**: **\u0915\u093f\u092f\u094b\u092e\u093f\u091c\u093c\u0942-\u0921\u0947\u0930\u093e** \u092e\u0902\u0926\u093f\u0930 \u0915\u0940 \u092f\u093e\u0924\u094d\u0930\u093e\u0964\n- **\u0926\u094b\u092a\u0939\u0930 \u0915\u093e \u092d\u094b\u091c\u0928 (12:00 - 13:30)**: **\u0928\u093f\u0936\u093f\u0915\u0940 \u092e\u093e\u0930\u094d\u0915\u0947\u091f** \u092e\u0947\u0902 \u0926\u094b\u092a\u0939\u0930 \u0915\u093e \u092d\u094b\u091c\u0928\u0964\n- **\u0926\u094b\u092a\u0939\u0930 (13:30 - 16:30)**: **\u0938\u093e\u0928\u0947\u0928\u091c\u093e\u0915\u093e \u0914\u0930 \u0928\u093f\u0928\u0947\u0928\u091c\u093e\u0915\u093e** \u0915\u0940 \u0917\u0932\u093f\u092f\u094b\u0902 \u092e\u0947\u0902 \u091f\u0939\u0932\u0947\u0902\u0964\n- **\u0936\u093e\u092e (17:30 - 20:00)**: **\u092f\u093e\u0938\u093e\u0915\u093e \u0936\u094d\u0930\u093e\u0907\u0928** \u092e\u0947\u0902 \u0938\u094d\u0925\u093e\u0928\u0940\u092f \u0938\u094d\u0925\u0932 \u092a\u0930 \u0938\u0902\u0927\u094d\u092f\u093e \u0915\u093e \u0906\u0928\u0902\u0926\u0964",
        "checklist": "- [x] \u092c\u0938 \u0914\u0930 \u0938\u092c\u0935\u0947 \u096b-\u0926\u093f\u0935\u0938\u0940\u092f \u092a\u093e\u0938 \u0915\u094d\u0930\u094d\u092f \u0915\u0930\u0947\u0902\u0964\n- [ ] \u091a\u093e\u092f \u0938\u092e\u093e\u0930\u094b\u0939 \u0915\u093e \u0938\u092e\u092f \u092c\u0941\u0915 \u0915\u0930\u0947\u0902\u0964\n- [x] \u0930\u093f\u092f\u094b\u0915\u093e\u0928 (Ryokan) \u0939\u094b\u091f\u0932 \u092c\u0941\u0915\u093f\u0902\u0917 \u0915\u0940 \u091c\u093e\u0928\u0915\u093e\u0930\u0940 \u0938\u0939\u0947\u091c\u0947\u0902\u0964\n- [ ] \u091a\u0932\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u090e\u0915 \u0906\u0930\u093e\u092e\u0926\u093e\u092f\u0915 \u091c\u0942\u0924\u0947 \u092a\u0939\u0928\u0947\u0902\u0964"
    },
    "Telugu": {
        "attractions": "1. **\\u0c2b\\u0c41\\u0c37\\u0c3f\\u0c2e\\u0c3f \\u0c07\\u0c28\\u0c3e\\u0c30\\u0c3f \\u0c06\\u0c32\\u0c2f\\u0c02**: \\u0c2a\\u0c30\\u0c4d\\u0c35\\u0c24\\u0c02 \\u0c2a\\u0c48\\u0c15\\ి \\u0c35\\ె\\u0c33\\్\\u0c32\\u0c47 \\u0c35\\ే\\u0c32\\ా\\u0c26\\ి \\u0c0f\\u0c30\\u0c41\\u0c2a\\ు \\u0c30\\u0c02\\u0c17\\ు \\u0c24\\u0c4b\\u0c30\\u0c3f \\u0c17\\ే\\u0c1f\\u0c4d\\u0c32\\u0c15\\u0c41 \\u0c2a\\u0c4d\\u0c30\\u0c38\\ి\\u0c26\\్\\ధ\\ి \\u0c1a\\ె\\u0c02\\u0c26\\u0c3f\\u0c28 \\u0c06\\u0c32\\u0c2f\\u0c02.\\n2. **\\u0c15\\u0c3f\\u0c02\\u0c15\\u0c3e\\u0c15\\u0c41-\\u0c1c\\u0c3f (\\u0c2c\\u0c02\\u0c17\\u0c3e\\u0c30\\u0c41 \\u0c2a\\్\\ర\\ా\\ల\\ే\\స\\్)**: \\u0c1a\\ె\\u0c30\\u0c41\\u0c35\\u0c41 \\u0c28\\ీ\\u0c1f\\u0c3f\\u0c32\\ో \\u0c2a\\u0c4d\\u0c30\\u0c24\\u0c3f\\బ\\u0c3f\\u0c02\\u0c2c\\u0c3f\\ం\\చ\\ే, \\u0c2c\\u0c02\\u0c17\\u0c3e\\u0c30\\u0c41 \\u0c2a\\u0c42\\u0c24 \\u0c2a\\u0c42\\u0c38\\u0c3f\\u0c28 \\u0c05\\ద\\్\\u0c2d\\u0c41\\u0c24\\u0c2e\\u0c48\\u0c28 \\u0c1c\\u0c46\\u0c28\\్ \\u0c2c\\u0c4c\\u0c26\\్\\u0c27 \\u0c06\\u0c32\\u0c2f\\u0c02.\\n3. **\\u0c05\\u0c30\\u0c3e\\u0c37\\u0c3f\\u0c2f\\u0c3e\\u0c2e\\u0c3e \\u0c35\\u0c46\\u0c26\\u0c41\\u0c30\\u0c41 \\u0c05\\u0c21\\u0c35\\u0c3f**: \\u0c2a\\u0c4a\\u0c21\\u0c35\\u0c48\\u0c28 \\u0c35\\u0c46\\u0c26\\u0c41\\u0c30\\u0c41 \\u0c1a\\ె\\u0c1f\\u0c4d\\u0c32\\u0c44 \\u0c2e\\u0c27\\u0c4d\\u0c2f \\u0c2a\\u0c4d\\u0c30\\u0c36\\u0c3e\\u0c02\\u0c24\\u0c2e\\u0c48\\u0c28 \\u0c28\\u0c21\\u0c15 \\u0c2e\\ా\\u0c30\\u0c4d\\u0c17\\ం.\\n4. **\\u0c15\\u0c3f\\u0c2f\\u0c4b\\u0c2e\\u0c3f\\u0c1c\\u0c41-\\u0c26\\u0c47\\u0c30\\u0c3e**: \\u0c15\\u0c4d\\u0c2f\\u0c4b\\u0c1f\\u0c4b \\u0c28\\u0c17\\u0c30\\u0c02 \\u0c2e\\ూ\\u0c32\\u0c4d\\య\\ం \\u0c15\\u0c28\\u0c3f\\u0c2a\\u0c3f\\ం\\చ\\ే \\u0c1a\\u0c3e\\u0c30\\u0c3f\\u0c24\\u0c4d\\u0c30\\u0c3e\\u0c24\\u0c4d\\u0c2e\\u0c15 \\u0c1a\\ె\\క\\్\\క \\u0c06\\u0c32\\u0c2f\\u0c02.",
        "culinary": "- **\\u0c28\\u0c3f\\u0c37\\u0c3f\\u0c15\\u0c3f \\u0c2e\\u0c3e\\u0c30\\u0c4d\\u0c15\\u0c46\\u0c1f\\u0c4d**: 400 \\u0c38\\u0c02\\u0c35\\u0c24\\u0c4d\\స\\u0c28\\u0c3f\\u0c37\\u0c3f\\u0c15\\u0c3f \\u0c2e\\u0c3e\\u0c30\\u0c4d\\u0c15\\u0c46\\u0c1f\\u0c4d**: 400 \\u0c38\\u0c02\\u0c35\\u0c24\\u0c4d\\స\\u0c30\\u0c3e\\u0c32 \\u0c1a\\u0c3e\u0c30\\u0c3f\\u0c24\\u0c4d\\u0c30\\u0c3e\\u0c24\\u0c4d\\u0c2e\\u0c15 \\u0c24\\u0c3f\\న\\ు\\బ\\u0c02\\u0c21\\u0c3e\\u0c32 \\u0c35\\ీ\\u0c27\\ి.\\n- **\\u0c17\\u0c3f\\u0c2f\\u0c3e\\u0c28\\u0c4d \\u0c32\\u0c4b \\u0c2e\\u0c1a\\\u0c4d\\చ\\ా**: \\u0c1a\\u0c3e\\u0c30\\u0c3f\\u0c24\\u0c4d\\u0c30\\u0c3e\\u0c24\\u0c4d\\u0c2e\\u0c15 \\u0c17\\u0c3f\\u0c2f\\u0c3e\\u0c28\\u0c4d \\u0c2a\\u0c4d\\u0c30\\ా\\ం\\త\\u0c02\\u0c32\\ో \\u0c26\\u0c4a\\ర\\ి\\క\\ే \\u0c28\\u0c3f\\జ\\u0c2e\\ై\\u0c28 \\u0c09\\u0c1c\\u0c3f \\u0c2e\\u0c1a\\\u0c4d\\చ\\ా \\u0c17\\్\\ర\\ీ\\న\\u0c4d \\u0c1f\\ీ \\u0c38\\్\\వ\\ీ\\ట\\్\\ల\\ు.\\n- **\\u0c15\\u0c4d\\u0c2f\\u0c4b\\u0c1f\\u0c4b \\u0c30\\u0c3e\\u0c2e\\ె\\u0c28\\్**: \\u0c38\\u0c4d\\u0c25\\u0c3e\\u0c28\\u0c3f\\u0c15 \\u0c26\\ు\\క\\ా\\ణ\\ా\\u0c32\\u0c32\\ో \\u0c32\\u0c2d\\u0c3f\\ం\\చ\\ే \\u0c05\\u0c22\\్\\u0c2d\\u0c41\\u0c24\\u0c2e\\u0c48\\u0c28 \\u0c2e\\u0c30\\u0c3f\\u0c2f\\u0c41 \\u0c30\\u0c41\\చ\\ి\\u0c15\\u0c30\\u0c2e\\u0c48\\u0c28 \\u0c30\\u0c3e\\u0c2e\\ె\\u0c28\\్ \\u0c28\\ూ\\u0c21\\u0c41\\u0c32\\u0c4d\\స\\్.",
        "tips": "- **\\u0c30\\u0c26\\u0c4d\\u0c26\\u0c40 \\u0c28\\u0c3f\\u0c35\\u0c3e\\u0c30\\u0c23**: \\u0c2a\\u0c4d\\u0c30\\u0c36\\u0c3e\\u0c02\\u0c24\\u0c2e\\u0c48\\u0c28 \\u0c35\\u0c3e\\u0c24\\u0c3e\\u0c35\\u0c30\\u0c23\\u0c02 \\u0c15\\u0c4b\\u0c38\\u0c02 \\u0c38\\ూ\\u0c30\\u0c4d\\u0c2f\\u0c4b\\u0c26\\u0c2f \\u0c38\\u0c2e\\u0c2f\\u0c02\u0c32\u0c4b (\\u0c09\\u0c26\\u0c2f\\u0c02 6:30 \\u0c17\\u0c02\\u0c1f\\u0c32\\u0c15\\u0c41) \\u0c2b\\u0c41\\u0c37\\u0c3f\\u0c2e\\u0c3f \\u0c07\\u0c28\\u0c3e\\u0c30\\u0c3f \\u0c26\\u0c30\\u0c4d\\u0c36\\u0c3f\\u0c02\\చ\\u0c02\\u0c21\\u0c3f.\\n- **\\u0c30\\u0c35\u0c3e\\u0c23\u0c3e**: \\u0c38\\u0c41\\u0c32\\u0c2d\\u0c2e\\u0c48\\u0c28 \\u0c2a\\u0c4d\\u0c30\\u0c2f\\u0c3e\\u0c23\u0c3e\u0c28\u0c3f\u0c15\u0c3f \\u0c10\\క\\ో\\క\\ా (ICOCA) \\u0c15\u0c3e\u0c30\u0c4d\u0c2d\u0c41\u0c28\u0c41 \\u0c15\u0c4a\u0c28\u0c41\u0c17\u0c3b\u0c32\u0c41 \\u0c1a\u0c47\u0c2f\u0c02\u0c21\u0c3f.\\n- **\\u0c2e\\u0c30\u0c4d\u0c2f\u0c3e\u0c26\u0c32\u0c41**: \\u0c17\u0c3f\u0c2f\u0c3e\u0c28\u0c4d \\u0c35\u0c40\u0c27\u0c41\u0c32\u0c4d\u0c32\u0c41\u0c32\u0c4b \\u0c17\u0c40\u0c37\u0c3e\u0c32 \\u0c2a\u0c4d\u0c30\u0c48\u0c35\u0c3f\u0c28\u0c41 \\u0c17\u0c4c\u0c30\u0c35\u0c3f\u0c28\u0c41\u0c21\u0c3f, \\u0c05\u0c28\u0c41\u0c2e\u0c41\u0c3f \\u0c32\u0c47\u0c15\u0c41\u0c02\u0c21\u0c3f \\u0c2b\u0c4b\u0c1f\u0c4d\u0c32\u0c41 \\u0c24\u0c40\u0c3f\u0c2f\u0c15\u0c02\u0c21\u0c3f.",
        "saving_tips": "- \\u0c15\\u0c4d\\u0c2f\\u0c4b\\u0c1f\\u0c4b \\u0c38\\u0c2c\u0c4d\\u200d\\u0c35\u0c47 \\u0c2e\\u0c30\\u0c3f\\u0c2f\\u0c41 \\u0c2c\u0c38\u0c4d\u0c38\u0c41 \\u0c15\u0c4a\u0c28\u0c41\u0c17\u0c3b\u0c32\u0c41 \\u0c1a\u0c47\u0c3f\u0c38\u0c41\u0c15\u0c4b\u0c02\u0c21\u0c3f.\\n- \\u0c2b\u0c4d\u0c2f\u0c3e\u0c35\u0c3f\u0c32\u0c41\u0c2e\u0c3e\u0c30\u0c4d\u0c15\u0c4d\u0c32\u0c4d\u0c32\u0c41 \\u0c32\u0c47\u0c15\u0c41\u0c02\u0c21\u0c3f \\u0c32\u0c3e\u0c38\u0c28\u0c4d \\u0c35\u0c02\u0c1f\u0c3f \\u0c15\u0c28\u0c4d\u0c35\u0c40\u0c28\u0c3f\u0c2f\u0c28\u0c4d\u0c38\u0c4d \\u0c38\u0c4d\u0c3f\u0c4d\u0c30\u0c4d\u0c32\u0c32\u0c4d\u0c32\u0c32\u0c4b \\u0c26\u0c4a\u0c30\u0c3f\u0c15\u0c47 \\u0c12\u0c28\u0c3f\u0c17\u0c3f\u0c30\u0c3f\u0c24\u0c4d\u0c30 \\u0c1a\u0c4c\u0c15\u0c3e \\u0c1f\u0c3f\u0c2b\u0c3f\u0c28\u0c4d \\u0c1a\u0c47\u0c3f\u0c2f\u0c02\u0c21\u0c3f.\\n- \u0c2b\u0c41\u0c31\u0c3f \u0c05\u0c28\u0c4d\u0c28\u0c3e\u0c30\u0c3f \u0c2e\u0c30\u0c3f\u0c3f\u0c41 \u0c2f\u0c38\u0c3e\u0c15\u0c3e \u0c06\u0c32\u0c2f\u0c3e\u0c32 \u0c26\u0c30\u0c4d\u0c36\u0c3f\u0c28\u0c02 \u0c2a\u0c42\u0c30\u0c4d\u0c32\u0c3f\u0c37\u0c3e \u0c0a\u0c15\u0c3f\u0c24\u0c02!",
        "itinerary_day1": "- **\\u0c09\\u0c26\\u0c2f\\u0c02 (07:00 - 11:30)**: \\u0c30\\u0c26\\u0c4d\\u0c26\\u0c40 \\u0c32\\u0c47\\u0c15\\u0c41\\u0c02\\u0c21\\u0c3e \\u0c2a\\u0c4d\\u0c30\\u0c36\\u0c3e\\u0c02\\u0c24\\u0c2e\\u0c48\\u0c28 \\u0c1a\u0c3e\u0c30\u0c3f\u0c24\u0c4d\u0c30\u0c3e\u0c34\u0c4d\u0c3e\u0c15 \\u0c2b\\u0c41\\u0c37\\u0c3f\\u0c2e\\u0c3f \\u0c07\\u0c28\\u0c3e\\u0c30\\u0c3f \\u0c06\\u0c32\\u0c2f\u0c3e\u0c28\u0c4d\u0c28\u0c3f \\u0c26\u0c30\u0c4d\u0c36\u0c3f\u0c3f\u0c15\u0c02\u0c21\u0c3f.\\n- **\\u0c2e\\u0c27\\u0c4d\\u0c2f\\u0c3e\\u0c39\\u0c4d\\u0c28 \\u0c2d\\u0c4b\\u0c1c\\u0c28\\u0c02 (12:00 - 13:30)**: **\\u0c28\\u0c3f\\u0c37\\u0c3f\\u0c15\\u0c3f \\u0c2e\\u0c3e\\u0c30\\u0c4d\\u0c15\\u0c46\\u0c1f\\u0c4d** \\u0c32\\u0c4b \\u0c38\\u0c4d\\u0c25\\u0c3e\u0c3f\u0c15 \u0c35\\u0c02\u0c1f\u0c15\u0c3e\u0c32\u0c28\u0c41 \u0c30\\u0c41\u0c1a\u0c3f \u0c1a\u0c42\u0c3f\u0c28\u0c02\u0c21\u0c3f.\\n- **\\u0c2e\\u0c27\\u0c4d\\u0c2f\\u0c3e\\u0c39\\u0c4d\\u0c28\\u0c02 (14:00 - 17:00)**: \\u0c38\\u0c4d\\u0c35\\u0c30\\u0c4d\\u0c23 \\u0c26\\u0c47\u0c3e\u0c32\u0c3e\u0c32\u0c02 **\\u0c15\\u0c3f\\u0c02\\u0c15\\u0c3e\\u0c15\\u0c41-\\u0c1c\\u0c3f** \\u0c26\\u0c30\\u0c4d\u0c36\u0c3f\u0c3f\u0c15\u0c02\u0c21\u0c3f.\\n- **\\u0c38\\u0c3e\\u0c2f\\u0c02\\u0c24\\u0c4d\u0c30\u0c02 (18:00 - 20:30)**: \\u0c1a\\u0c3e\u0c30\u0c3f\u0c24\u0c4d\u0c30\u0c3e\u0c34\u0c4d\u0c3e\u0c15 **\\u0c17\\u0c3f\\u0c2f\\u0c3e\\u0c28\\u0c4d** \\u0c35\\u0c40\u0c27\u0c41\u0c32\u0c4d\u0c32\u0c41\u0c32\u0c4b \\u0c24\\u0c3f\u0c30\u0c41\u0c17\u0c42\u0c32\u0c42 \\u0c30\\u0c3e\u0c2e\u0c46\u0c28\u0c4d \\u0c28\u0c42\u0c3f\u0c32\u0c4d\u0c38 \\u0c24\\u0c3f\u0c3f\u0c28\u0c3f \\u0c06\u0c28\u0c02\u0c28\u0c3f\u0c3f\u0c15\u0c02\u0c21\u0c3f.",
        "itinerary_day2": "- **\\u0c09\\u0c26\\u0c2f\\u0c02 (07:30 - 11:00)**: \\u0c2a\\u0c4d\\u0c30\\u0c36\\u0c3e\\u0c02\\u0c24\\u0c2e\\u0c48\\u0c28 **\\u0c05\\u0c30\\u0c3e\\u0c37\\u0c3f\\u0c2f\\u0c3e\\u0c2e\u0c3e \u0c35\u0c46\u0c26\u0c41\u0c30\u0c41 \u0c05\u0c28\u0c3f\u0c32\u0c3f** \\u0c32\\u0c4b \\u0c35\u0c3f\u0c37\u0c3f\u0c38\u0c3f\u0c3f\u0c15\u0c02\u0c21\u0c3f.\\n- **\\u0c2e\\u0c27\\u0c4d\\u0c2f\\u0c3e\\u0c39\\u0c4d\\u0c28 \\u0c2d\\u0c4b\\u0c1c\\u0c28\\u0c02 (11:30 - 13:00)**: \\u0c28\\u0c26\u0c40 \u0c24\u0c40\u0c30\u0c02\u0c32\u0c41 \\u0c38\u0c3e\u0c02\u0c2a\u0c4d\u0c30\u0c26\u0c3e\u0c2f\u0c15 \u0c38\u0c4b\u0c3f\u0c2f\u0c3e\u0c2c\u0c3f\u0c28\u0c4d \u0c35\\u0c02\u0c1f\u0c15\u0c02 (\\u0c2f\u0c41\u0c26\u0c40\u0c2b\u0c41) \\u0c24\\u0c3f\u0c3f\u0c28\u0c02\u0c21\u0c3f.\\n- **\\u0c2e\\u0c27\\u0c4d\\u0c2f\\u0c3e\\u0c39\\u0c4d\\u0c28\\u0c02 (13:30 - 16:30)**: \\u0c2e\u0c02\u0c15\u0c40 \u0c2a\u0c3e\u0c30\u0c4d\u0c15\u0c4d \\u0c26\\u0c30\\u0c4d\u0c36\u0c3f\u0c3f\u0c15\u0c3f\u0c3f \\u0c38\u0c3e\u0c02\u0c2a\u0c4d\u0c30\u0c26\u0c3e\u0c2f \u0c24\u0c47\u0c3f\u0c28\u0c40\u0c3f\u0c30\u0c3f \u0c35\\u0c47\u0c11\u0c28\u0c41\u0c15 \\u0c1f\u0c40 \u0c38\u0c46\u0c30\u0c3f\u0c2e\u0c28\u0c40 \\u0c32\\u0c4b \\u0c2a\\u0c3e\u0c32\u0c4d\u0c17\u0c40\u0c26\u0c02\u0c21\u0c3f.\\n- **\\u0c38\\u0c3e\\u0c2f\\u0c02\\u0c24\\u0c4d\u0c30\u0c02 (17:30 - 20:30)**: \\u0c05\\u0c02\\u0c26\\u0c2e\\u0c48\\u0c28 **\\u0c2a\\u0c4a\\u0c02\\u0c1f\\u0c4b\\u0c1a\\u0c4b \\u0c17\\u0c22\u0c4d\u0c32\u0c41** \\u0c32\\u0c4b \\u0c28\\u0c26\u0c41\u0c38\u0c4d\u0c32\u0c41 \\u0c21\u0c3f\u0c28\u0c4d\u0c30\u0c4d \\u0c1a\u0c47\u0c3f\u0c02\u0c21\u0c3f.",
        "itinerary_day3": "- **\\u0c09\\u0c26\\u0c2f\\u0c02 (08:30 - 11:30)**: \\u0c05\\u0c26\\u0c4d\\u0c2d\\u0c41\\u0c24\\u0c2e\\u0c48\\u0c28 \\u0c35\\u0c4d\\u0c2f\\u0c42\u0c38\u0c4d \\u0c15\u0c28\u0c3f\u0c2a\u0c3f\u0c02\u0c15\u0c47 **\\u0c15\u0c3f\u0c2f\u0c4b\u0c2e\u0c3f\u0c15\u0c31-\\u0c26\u0c47\u0c30\u0c3e \u0c06\u0c32\u0c2f\u0c3e\u0c28\u0c4d\u0c28\u0c3f** \\u0c38\u0c02\u0c26\u0c30\u0c4d\u0c36\u0c3f\u0c3f\u0c15\u0c02\u0c21\u0c3f.\\n- **\\u0c2e\\u0c27\\u0c4d\\u0c2f\\u0c3e\\u0c39\\u0c4d\\u0c28 \\u0c2d\\u0c4b\\u0c1c\\u0c28\\u0c02 (12:00 - 13:30)**: \\u0c38\u0c3e\u0c02\u0c2a\u0c4d\u0c30\u0c26\u0c3e\u0c2f \u0c38\u0c4b\u0c3e\u0c30 \u0c28\u0c42\u0c3f\u0c32\u0c4d\u0c32\u0c41\u0c38\u0c4d \u0c30\\u0c41\u0c1a\u0c3f \u0c1a\u0c42\u0c3f\u0c28\u0c02\u0c21\u0c3f.\\n- **\\u0c2e\\u0c27\\u0c4d\\u0c2f\\u0c3e\\u0c39\\u0c4d\\u0c28\\u0c02 (13:30 - 16:30)**: \\u0c1a\u0c3e\u0c30\u0c3f\u0c24\u0c4d\u0c30\u0c3e\u0c34\u0c4d\u0c3e\u0c15 **\\u0c38\u0c3e\u0c28\u0c47\u0c28\u0c4d\u0c17\u0c3e\u0c15\u0c3e \u0c2e\\u0c30\\u0c3f\\u0c2f\\u0c41 \u0c28\\u0c3f\\u0c28\u0c47\u0c30\u0c4d\u0c17\u0c3e\u0c15\u0c3e** \u0c35\u0c40\u0c27\u0c41\u0c32\u0c4d\u0c32\u0c41\u0c32\u0c4b \u0c37\u0c3e\u0c30\u0c3f\u0c02\u0c17\u0c4d \u0c1a\u0c47\u0c3f\u0c02\u0c21\u0c3f.\\n- **\\u0c38\\u0c3e\u0c2f\u0c02\\u0c24\\u0c4d\u0c30\u0c02 (17:30 - 20:00)**: \\u0c38\u0c42\u0c30\u0c4d\u0c32\u0c3e\u0c38\u0c4d\u0c24\u0c2e\u0c02 \u0c35\u0c47\u0c32\u0c41 **\\u0c2f\u0c38\u0c3e\u0c15\u0c3e \u0c06\u0c32\u0c2f\u0c3e\u0c28\u0c4d\u0c28\u0c3f** \\u0c26\\u0c30\\u0c4d\u0c36\u0c3f\u0c3f\u0c15\u0c02\u0c21\u0c3f \u0c28\u0c26\u0c40 \u0c24\u0c40\u0c30\u0c3e\u0c30 \u0c17\u0c21\u0c3f\u0c2a\u0c02\u0c21\u0c3f.",
        "checklist": "- [x] \\u0c2c\\u0c38\\u0c4d\\u0c38\\u0c41 \\u0c2e\\u0c30\\u0c3f\\u0c2f\\u0c41 \\u0c38\\u0c2c\\u0c4d\\u200c\\u0c35\\u0c47 1-\\u0c30\\u0c4b\\u0c1c\u0c41 \u0c2a\u0c3e\u0c30\u0c4d \u0c15\\u0c4a\u0c28\u0c41\u0c17\u0c3b\u0c32\u0c41 \u0c1a\u0c47\u0c3f\u0c02\u0c21\u0c3f.\\n- [ ] \\u0c05\\u0c30\\u0c3e\\u0c37\\u0c3f\\u0c2f\u0c3e\\u0c2e\u0c3e \u0c32\u0c41 \u0c1f\u0c40 \u0c38\u0c46\u0c30\u0c3f\u0c2e\u0c28\u0c40 \u0c28\u0c3f \u0c2c\u0c41\u0c15\u0c4d \u0c1a\u0c47\u0c3f\u0c02\u0c21\u0c3f.\\n- [x]  \\u0c39\\u0c4b\u0c1f\u0c32\u0c4d \u0c2c\u0c41\u0c15\u0c3f\u0c02\u0c17\u0c4d \u0c35\u0c3f\u0c3f\u0c30\u0c3e\u0c32\u0c28\u0c41 \u0c2f\u0c4b\u0c28\u0c4d \u0c32\u0c41 \u0c2e\u0c26\u0c4d\u0c30\u0c30\u0c2a\u0c30\u0c31\u0c3f\u0c15\u0c4b\u0c02\u0c21\u0c3f.\\n- [ ] \\u0c28\\u0c26\u0c3f\u0c31\u0c3f\u0c28\u0c3f\u0c15\u0c3f \u0c38\u0c4c\u0c15\u0c30\u0c4d\u0c32\u0c4d\u0c32\u0c3e\u0c28\u0c4d\u0c32\u0c02\u0c15\u0c3e \u0c09\u0c02\u0c32\u0c47 \u0c37\u0c42\u0c38\u0c4f \u0c38\u0c3f\u0c26\u0c4d\u0c32\u0c02 \u0c1a\u0c47\u0c3f\u0c38\u0c41\u0c15\u0c4b\u0c02\u0c21\u0c3f."
    },
}

# Helper to fetch localization terms
def get_translated_terms(lang: str) -> dict:
    if lang in translations:
        merged = english_defaults.copy()
        for k, v in translations[lang].items():
            merged[k] = v
        return merged
    return english_defaults


class MockChatOpenAI:
    def invoke(self, messages):
        system_content = ""
        for msg in messages:
            if hasattr(msg, "content"):
                system_content = msg.content
                break
        content = get_mock_response(system_content)
        return AIMessage(content=content)

# 3. LLM Selection logic (OpenAI vs. Mock Simulation)
openai_key = os.environ.get("OPENAI_API_KEY")
is_mock = True
if openai_key and openai_key.strip() and not openai_key.startswith("your_"):
    llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
    is_mock = False
else:
    llm = MockChatOpenAI()

# 4. Define the Travel Researcher Agent Node
def researcher_agent(state: AgentState):
    destination = state["destination"]
    interests = ", ".join(state["interests"])
    language = state.get("language", "English")
    
    prompt = f"""You are an expert travel researcher. Research top attractions, local food, 
    and travel tips for {destination} tailored to interests like: {interests}. 
    Provide a concise, highly informative summary.
    Respond in the language: {language}.
    Ensure the keyword 'language: {language}' is clearly defined in the instruction so fallback mock agents can read it."""
    
    response = llm.invoke([SystemMessage(content=prompt)])
    
    return {
        "research_notes": response.content,
        "next_step": "budget"
    }

# 5. Define the Budget Manager Agent Node
def budget_agent(state: AgentState):
    destination = state["destination"]
    duration = state["duration_days"]
    interests = ", ".join(state["interests"])
    budget_limit = state.get("budget_limit", 1000.0)
    currency = state.get("currency", "USD")
    language = state.get("language", "English")
    
    prompt = f"""You are an expert travel budget manager. Estimate the total costs for a {duration}-day trip to {destination} with interests: {interests}.
    Provide a breakdown of lodging, dining, transit, and activities.
    Budget Limit: {budget_limit} {currency}.
    All estimations and totals MUST be in the currency: {currency}.
    Structure the output with clear sections and a table format where appropriate.
    Respond in the language: {language}.
    Ensure the keywords 'currency: {currency}' and 'language: {language}' are clearly defined in the instruction so fallback mock agents can read it."""
    
    response = llm.invoke([SystemMessage(content=prompt)])
    
    return {
        "budget_notes": response.content,
        "next_step": "planner"
    }

# 6. Define the Itinerary Planner Agent Node
def itinerary_planner_agent(state: AgentState):
    destination = state["destination"]
    duration = state["duration_days"]
    currency = state.get("currency", "USD")
    language = state.get("language", "English")
    notes = state["research_notes"]
    budget = state["budget_notes"]
    
    prompt = f"""You are an expert travel itinerary planner. Create a highly structured, 
    day-by-day itinerary for a {duration}-day trip to {destination}. 
    Use the following research notes:\n\n{notes}\n\nAnd budget notes:\n\n{budget}\n\nCombine both to create a day-by-day itinerary with estimated costs included for each major item in the currency: {currency}.
    Respond in the language: {language}.
    Ensure the keywords 'currency: {currency}' and 'language: {language}' are clearly defined in the instruction so fallback mock agents can read it."""
    
    response = llm.invoke([SystemMessage(content=prompt)])
    
    return {
        "final_itinerary": response.content,
        "next_step": "end"
    }

# 7. Define Routing Logic
def route_next(state: AgentState) -> Literal["researcher", "budget", "planner", END]:
    next_step = state.get("next_step")
    if next_step == "budget":
        return "budget"
    elif next_step == "planner":
        return "planner"
    elif next_step == "end":
        return END
    return "researcher"

# 8. Define Mock Response logic inside the Mock LLM class
def get_city_attractions(city_name):
    try:
        summary = wikipedia.summary(f"Tourism in {city_name}", sentences=3)
        return summary
    except Exception:
        try:
            summary = wikipedia.summary(city_name, sentences=3)
            return summary
        except Exception as e:
            return f"Popular destination known for its cultural heritage, dining, and scenic locations."

def get_backup_directions(start_place, end_place, language="English"):
    start_clean = start_place.lower().strip()
    end_clean = end_place.lower().strip()
    
    kyoto_station_fushimi = "kyoto station" in start_clean and "fushimi inari" in end_clean
    kyoto_station_arashiyama = "kyoto station" in start_clean and "arashiyama" in end_clean
    fushimi_kiyomizu = "fushimi inari" in start_clean and "kiyomizu" in end_clean
    
    routes_db = {
        "English": {
            "k_fushimi": [
                "Take the JR Nara Line from Kyoto Station to Inari Station (5 mins, 2.7 km).",
                "Exit Inari Station and walk east toward the main shrine gate (3 mins, 200m)."
            ],
            "k_arashiyama": [
                "Take the JR San-in Line from Kyoto Station to Saga-Arashiyama Station (15 mins, 10 km).",
                "Walk west along the main road to the Bamboo Grove entrance (10 mins, 800m)."
            ],
            "f_kiyomizu": [
                "Take the Keihan Main Line from Fushimi-Inari Station to Kiyomizu-Gojo Station (8 mins, 3.5 km).",
                "Walk east up the hill toward Kiyomizu-dera Temple (20 mins, 1.2 km)."
            ],
            "default": [
                f"Depart from {start_place} toward the nearest transit hub.",
                f"Take the local train or bus line heading toward {end_place}.",
                f"Arrive at {end_place} and follow local signs to the entrance."
            ]
        },
        "Spanish": {
            "k_fushimi": [
                "Tome la línea JR Nara desde la estación de Kioto hasta la estación de Inari (5 min, 2.7 km).",
                "Salga de la estación de Inari y camine hacia el este hacia la puerta principal del santuario (3 min, 200m)."
            ],
            "k_arashiyama": [
                "Tome la línea JR San-in desde la estación de Kioto hasta la estación de Saga-Arashiyama (15 min, 10 km).",
                "Camine hacia el oeste por la calle principal hacia la entrada del bosque de bambú (10 min, 800m)."
            ],
            "f_kiyomizu": [
                "Tome la línea principal de Keihan desde la estación Fushimi-Inari hasta la estación Kiyomizu-Gojo (8 min, 3.5 km).",
                "Camine hacia el este subiendo la colina hacia el templo Kiyomizu-dera (20 min, 1.2 km)."
            ],
            "default": [
                f"Salga de {start_place} hacia el centro de transporte más cercano.",
                f"Tome el tren o autobús local en dirección a {end_place}.",
                f"Llegue a {end_place} y siga las señales hacia la entrada."
            ]
        },
        "Japanese": {
            "k_fushimi": [
                "京都駅からJR奈良線で稲荷駅へ移動します (約5分, 2.7 km)。",
                "稲荷駅を出て、東の本殿方面へ徒歩で進みます (約3分, 200m)。"
            ],
            "k_arashiyama": [
                "京都駅からJR山陰本線で嵯峨嵐山駅へ移動します (約15分, 10 km)。",
                "メイン通りを西へ竹林の小径の入口方面へ歩きます (約10分, 800m)。"
            ],
            "f_kiyomizu": [
                "伏見稲荷駅から京阪本線で清水五条駅へ移動します (約8分, 3.5 km)。",
                "東の坂道を清水寺方面へ歩いて上ります (約20分, 1.2 km)。"
            ],
            "default": [
                f"{start_place}を出発し、最寄りの公共交通機関に向かいます。",
                f"{end_place}行きのローカル線またはバスに乗車します。",
                f"{end_place}に到着後、案内標識に従って入口へ向かいます。"
            ]
        },
        "French": {
            "k_fushimi": [
                "Prendre la ligne JR Nara de la gare de Kyoto à la gare d'Inari (5 min, 2.7 km).",
                "Sortir de la gare d'Inari et marcher vers l'est en direction de l'entrée du sanctuaire (3 min, 200m)."
            ],
            "k_arashiyama": [
                "Prendre la ligne JR San-in de la gare de Kyoto à la gare de Saga-Arashiyama (15 min, 10 km).",
                "Marcher vers l'ouest sur la rue principale vers l'entrée de la bambouseraie (10 min, 800m)."
            ],
            "f_kiyomizu": [
                "Prendre la ligne Keihan de la gare Fushimi-Inari à la gare Kiyomizu-Gojo (8 min, 3.5 km).",
                "Marcher vers l'est en montant la colline vers le temple Kiyomizu-dera (20 min, 1.2 km)."
            ],
            "default": [
                f"Départ de {start_place} vers le centre de transport le plus proche.",
                f"Prendre le bus ou le train local en direction de {end_place}.",
                f"Arriver à {end_place} et suivre les indications vers l'entrée."
            ]
        },
        "German": {
            "k_fushimi": [
                "Nehmen Sie die JR Nara-Linie vom Bahnhof Kyoto zum Bahnhof Inari (5 Min., 2,7 km).",
                "Verlassen Sie den Bahnhof Inari und gehen Sie nach Osten zum Haupttor des Schreins (3 Min., 200m)."
            ],
            "k_arashiyama": [
                "Nehmen Sie die JR San-in-Linie vom Bahnhof Kyoto zum Bahnhof Saga-Arashiyama (15 Min., 10 km).",
                "Gehen Sie auf der Hauptstraße nach Westen zum Eingang des Bambuswaldes (10 Min., 800m)."
            ],
            "f_kiyomizu": [
                "Nehmen Sie die Keihan-Hauptlinie vom Bahnhof Fushimi-Inari zum Bahnhof Kiyomizu-Gojo (8 Min., 3,5 km).",
                "Gehen Sie den Hügel hinauf nach Osten zum Kiyomizu-dera-Tempel (20 Min., 1,2 km)."
            ],
            "default": [
                f"Abfahrt von {start_place} zum nächsten Verkehrsknotenpunkt.",
                f"Nehmen Sie den Bus oder Zug in Richtung {end_place}.",
                f"Ankunft bei {end_place} und den Schildern zum Eingang folgen."
            ]
        },
        "Hindi": {
            "k_fushimi": [
                "क्यूशू स्टेशन से जेआर नारा लाइन लेकर इनारी स्टेशन पहुंचें (5 मिनट, 2.7 किमी)।",
                "इनारी स्टेशन से बाहर निकलें और पूर्व की ओर मुख्य मंदिर द्वार की तरफ चलें (3 मिनट, 200 मीटर)।"
            ],
            "k_arashiyama": [
                "क्यूशू स्टेशन से जेआर सैन-इन लाइन लेकर सागा-आराशियामा स्टेशन पहुंचें (15 मिनट, 10 किमी)।",
                "बांस के जंगल के प्रवेश द्वार की ओर मुख्य सड़क पर पश्चिम की ओर चलें (10 मिनट, 800 मीटर)।"
            ],
            "f_kiyomizu": [
                "फुशिमी-इनारी स्टेशन से केहान मेन लाइन लेकर कियोमिज़ु-गोजो स्टेशन पहुंचें (8 मिनट, 3.5 किमी)।",
                "कियोमिज़ु-डेरा मंदिर की ओर पूर्व की दिशा में पहाड़ी पर चढ़ें (20 मिनट, 1.2 किमी)।"
            ],
            "default": [
                f"{start_place} से निकटतम परिवहन केंद्र की ओर प्रस्थान करें।",
                f"{end_place} की ओर जाने वाली स्थानीय ट्रेन या बस लें।",
                f"{end_place} पर पहुंचें और मुख्य द्वार के लिए स्थानीय संकेतों का पालन करें।"
            ]
        },
        "Telugu": {
            "k_fushimi": [
                "క్యోటో స్టేషన్ నుండి జెఆర్ నారా లైన్ ద్వారా ఇనారి స్టేషన్‌కు వెళ్లండి (5 నిమిషాలు, 2.7 కిమీ).",
                "ఇనారి స్టేషన్ నుండి బయటకు వచ్చి ప్రధాన ఆలయ ద్వారం వైపు తూర్పుగా నడవండి (3 నిమిషాలు, 200 మీటర్లు)."
            ],
            "k_arashiyama": [
                "క్యోటో స్టేషన్ నుండి జెఆర్ శాన్-ఇన్ లైన్ ద్వారా సగా-అరాషియామా స్టేషన్‌కు వెళ్లండి (15 నిమిషాలు, 10 కిమీ).",
                "వెదురు అడవి ప్రవేశ ద్వారం వైపు ప్రధాన రహదారి వెంట పడమరగా నడవండి (10 నిమిషాలు, 800 మీటర్లు)."
            ],
            "f_kiyomizu": [
                "ఫుషిమి-ఇనారి స్టేషన్ నుండి కేహాన్ మెయిన్ లైన్ ద్వారా కియోమిజు-గోజో స్టేషన్‌కు వెళ్లండి (8 నిమిషాలు, 3.5 కిమీ).",
                "కియోమిజు-దెరా ఆలయం వైపు కొండపైకి తూర్పుగా నడవండి (20 నిమిషాలు, 1.2 కిమీ)."
            ],
            "default": [
                f"{start_place} నుండి సమీప రవాణా కేంద్రం వైపు బయలుదేరండి.",
                f"{end_place} వైపు వెళ్లే లోకల్ రైలు లేదా బస్సును ఎక్కండి.",
                f"{end_place} కి చేరుకుని ప్రధాన ద్వారం వైపు వెళ్లడానికి స్థానిక సూచనలను అనుసరించండి."
            ]
        }
    }
    
    lang_db = routes_db.get(language, routes_db["English"])
    if kyoto_station_fushimi:
        return lang_db["k_fushimi"]
    elif kyoto_station_arashiyama:
        return lang_db["k_arashiyama"]
    elif fushimi_kiyomizu:
        return lang_db["f_kiyomizu"]
    else:
        return lang_db["default"]

def get_clean_directions(start_place, end_place, language="English"):
    # 1. Google Directions API
    google_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if google_key and google_key.strip() and not google_key.startswith("your_"):
        try:
            url = "https://maps.googleapis.com/maps/api/directions/json"
            params = {
                "origin": start_place,
                "destination": end_place,
                "key": google_key
            }
            r = requests.get(url, params=params, verify=False, timeout=5).json()
            if r.get("status") == "OK" and r.get("routes"):
                steps = r["routes"][0]["legs"][0]["steps"]
                instructions = []
                for step in steps:
                    html_txt = step.get("html_instructions", "")
                    clean_txt = re.sub(r'<[^<]+?>', '', html_txt)
                    dist_text = step.get("distance", {}).get("text", "")
                    dur_text = step.get("duration", {}).get("text", "")
                    if dist_text or dur_text:
                        details = []
                        if dist_text:
                            details.append(dist_text)
                        if dur_text:
                            details.append(dur_text)
                        clean_txt += f" ({', '.join(details)})"
                    instructions.append(clean_txt)
                if instructions:
                    return instructions
        except Exception as e:
            print(f"Error fetching Google Directions: {e}")

    # 2. OSRM / Nominatim fallback
    try:
        start_url = f"https://nominatim.openstreetmap.org/search?format=json&q={urllib.parse.quote(start_place)}"
        start_headers = {"User-Agent": "AeroPlanTravelPlanner/1.0"}
        r1 = requests.get(start_url, headers=start_headers, verify=False, timeout=5).json()
        if r1:
            start_lon, start_lat = r1[0]["lon"], r1[0]["lat"]

            end_url = f"https://nominatim.openstreetmap.org/search?format=json&q={urllib.parse.quote(end_place)}"
            r2 = requests.get(end_url, headers=start_headers, verify=False, timeout=5).json()
            if r2:
                end_lon, end_lat = r2[0]["lon"], r2[0]["lat"]

                osrm_url = f"http://router.project-osrm.org/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=false&steps=true"
                r_osrm = requests.get(osrm_url, verify=False, timeout=5).json()
                if "routes" in r_osrm and r_osrm["routes"]:
                    steps = r_osrm['routes'][0]['legs'][0]['steps']
                    instructions = []
                    for step in steps:
                        m = step.get('maneuver', {})
                        m_type = m.get('type', '')
                        m_mod = m.get('modifier', '')
                        name = step.get('name', '')
                        dist = step.get('distance', 0)
                        
                        if m_type == 'depart':
                            txt = "Depart"
                            if m_mod and m_mod != 'uturn':
                                txt += f" heading {m_mod}"
                        elif m_type == 'arrive':
                            txt = "Arrive at destination"
                        elif m_type == 'turn':
                            txt = f"Turn {m_mod}" if m_mod else "Turn"
                        else:
                            txt = m_type.replace('_', ' ').capitalize()
                            if m_mod:
                                txt += f" {m_mod}"
                        if name:
                            txt += f" onto {name}"
                        if dist > 0:
                            txt += f" (for {int(dist)}m)"
                        instructions.append(txt)
                    if instructions:
                        return instructions
    except Exception as e:
        print(f"Error fetching OSRM directions: {e}")
        
    # 3. Mapped / Default Backup directions
    return get_backup_directions(start_place, end_place, language)

def get_itinerary_day_template(language, morning_spot, lunch_spot, afternoon_spot, evening_spot, evening_food, sym, cost_morning, cost_lunch, cost_afternoon, cost_evening):
    templates = {
        "Spanish": {
            "morning": f"- **Mañana (08:30 - 12:00)**: Visita el famoso {morning_spot}. Empiece temprano para evitar las multitudes. *(Est: {sym}{cost_morning})*",
            "lunch": f"- **Almuerzo (12:00 - 13:30)**: Almuerce en un mercado tradicional local y pruebe {lunch_spot}. *(Est: {sym}{cost_lunch})*",
            "afternoon": f"- **Tarde (13:30 - 17:00)**: Explore el hermoso {afternoon_spot} y pasee por sus alrededores. *(Est: {sym}{cost_afternoon})*",
            "evening": f"- **Noche (17:30 - 21:00)**: Visite {evening_spot} para disfrutar del ambiente nocturno y disfrute de una cena tradicional con {evening_food}. *(Est: {sym}{cost_evening})*"
        },
        "Japanese": {
            "morning": f"- **午前中 (08:30 - 12:00)**: 混雑を避けるため、早めに人気の{morning_spot}を訪問します。 *(見込み: {sym}{cost_morning})*",
            "lunch": f"- **昼食 (12:00 - 13:30)**: 地元の伝統市場で{lunch_spot}を味わいます。 *(見込み: {sym}{cost_lunch})*",
            "afternoon": f"- **午後 (13:30 - 17:00)**: 美しい{afternoon_spot}を散策し、周辺の魅力を探ります。 *(見込み: {sym}{cost_afternoon})*",
            "evening": f"- **夕方・夜 (17:30 - 21:00)**: 夜の雰囲気が素晴らしい{evening_spot}を訪れ、伝統的な{evening_food}の夕食を楽しみます。 *(見込み: {sym}{cost_evening})*"
        },
        "French": {
            "morning": f"- **Matin (08:30 - 12:00)**: Visitez le célèbre {morning_spot}. Partez tôt pour éviter la foule. *(Est: {sym}{cost_morning})*",
            "lunch": f"- **Déjeuner (12:00 - 13:30)**: Déjeunez dans un marché local traditionnel et goûtez {lunch_spot}. *(Est: {sym}{cost_lunch})*",
            "afternoon": f"- **Après-midi (13:30 - 17:00)**: Explorez le magnifique {afternoon_spot} et promenez-vous. *(Est: {sym}{cost_afternoon})*",
            "evening": f"- **Soirée (17:30 - 21:00)**: Visitez {evening_spot} pour l'ambiance nocturne et savourez un dîner traditionnel de {evening_food}. *(Est: {sym}{cost_evening})*"
        },
        "German": {
            "morning": f"- **Morgen (08:30 - 12:00)**: Besuchen Sie das berühmte {morning_spot}. Starten Sie früh, um Staus zu vermeiden. *(Est: {sym}{cost_morning})*",
            "lunch": f"- **Mittagessen (12:00 - 13:30)**: Essen Sie in einer traditionellen Markthalle und probieren Sie {lunch_spot}. *(Est: {sym}{cost_lunch})*",
            "afternoon": f"- **Nachmittag (13:30 - 17:00)**: Erkunden Sie das malerische {afternoon_spot} und wandern Sie umher. *(Est: {sym}{cost_afternoon})*",
            "evening": f"- **Abend (17:30 - 21:00)**: Besuchen Sie {evening_spot} für eine tolle Abendstimmung und genießen Sie ein Abendessen mit {evening_food}. *(Est: {sym}{cost_evening})*"
        },
        "Hindi": {
            "morning": f"- **सुबह (08:30 - 12:00)**: प्रसिद्ध {morning_spot} का दौरा करें। भीड़ से बचने के लिए जल्दी शुरुआत करें। *(अनुमानित लागत: {sym}{cost_morning})*",
            "lunch": f"- **दोपहर का भोजन (12:00 - 13:30)**: स्थानीय पारंपरिक बाजार में {lunch_spot} का स्वाद लें। *(अनुमानित लागत: {sym}{cost_lunch})*",
            "afternoon": f"- **दोपहर (13:30 - 17:00)**: सुंदर {afternoon_spot} का भ्रमण करें और आसपास के क्षेत्रों को देखें। *(अनुमानित लागत: {sym}{cost_afternoon})*",
            "evening": f"- **शाम (17:30 - 21:00)**: शाम के वातावरण का आनंद लेने के लिए {evening_spot} पर जाएं और स्वादिष्ट {evening_food} का भोजन करें। *(अनुमानित लागत: {sym}{cost_evening})*"
        },
        "Telugu": {
            "morning": f"- **ఉదయం (08:30 - 12:00)**: ప్రసిద్ధ {morning_spot} సందర్శించండి. రద్దీని నివారించడానికి త్వరగా ప్రారంభించండి. *(అంచనా వ్యయం: {sym}{cost_morning})*",
            "lunch": f"- **మధ్యాహ్న భోజనం (12:00 - 13:30)**: స్థానిక సాంప్రదాయ మార్కెట్‌లో {lunch_spot} రుచి చూడండి. *(అంచనా వ్యయం: {sym}{cost_lunch})*",
            "afternoon": f"- **మధ్యాహ్నం (13:30 - 17:00)**: అందమైన {afternoon_spot} చుట్టుపక్కల ప్రాంతాలను అన్వేషించండి. *(అంచనా వ్యయం: {sym}{cost_afternoon})*",
            "evening": f"- **సాయంత్రం (17:30 - 21:00)**: సాయంత్రపు ఆహ్లాదకర వాతావరణం కోసం {evening_spot} కి వెళ్ళి సాంప్రదాయ {evening_food} డిన్నర్ ఆస్వాదించండి. *(అంచనా వ్యయం: {sym}{cost_evening})*"
        },
        "English": {
            "morning": f"- **Morning (08:30 - 12:00)**: Visit the famous {morning_spot}. Start early to avoid the crowds. *(Est: {sym}{cost_morning})*",
            "lunch": f"- **Lunch (12:00 - 13:30)**: Have lunch in a traditional local market and try {lunch_spot}. *(Est: {sym}{cost_lunch})*",
            "afternoon": f"- **Afternoon (13:30 - 17:00)**: Explore the beautiful {afternoon_spot} and stroll around. *(Est: {sym}{cost_afternoon})*",
            "evening": f"- **Evening (17:30 - 21:00)**: Visit {evening_spot} for a lovely evening atmosphere and enjoy a dinner of {evening_food}. *(Est: {sym}{cost_evening})*"
        }
    }
    return templates.get(language, templates["English"])

def get_mock_response(system_content: str) -> str:
    intro_text = " ".join(system_content[:400].split())
    
    destination = "Kyoto, Japan"
    dest_match = re.search(r"(?:for|to)\s+([a-zA-Z\s,]+?)(?:\s+tailored|\s+with interests|\.|\n|$)", intro_text)
    if dest_match:
        destination = dest_match.group(1).strip()
        
    duration = 3
    dur_match = re.search(r"(\d+)-day", intro_text)
    if dur_match:
        duration = int(dur_match.group(1))
        
    interests = "Historical Temples, Street Food"
    interests_match = re.search(r"interests like:\s*(.*?)(?:\.|\n|$)", intro_text)
    if interests_match:
        interests = interests_match.group(1).strip()
        
    budget_limit = 1000.0
    budget_match = re.search(r"Limit:\s*([\d\.,]+)", system_content)
    if budget_match:
        try:
            budget_limit = float(budget_match.group(1).replace(",", ""))
        except ValueError:
            pass
            
    currency = "USD"
    curr_match = re.search(r"currency:\s*([A-Z]{3})", system_content)
    if curr_match:
        currency = curr_match.group(1).strip()
        
    language = "English"
    lang_match = re.search(r"language:\s*([a-zA-Z]+)", system_content)
    if lang_match:
        language = lang_match.group(1).strip()

    rate, sym = exchange_rates.get(currency, (1.0, "$"))
    t = get_translated_terms(language)
    
    is_kyoto = "kyoto" in destination.lower()
    
    # Predefined popular cities DB
    db = {
        "paris": {
            "attractions": ["Eiffel Tower", "Louvre Museum", "Notre-Dame Cathedral", "Arc de Triomphe", "Seine River Cruise", "Sacre-Coeur Basilica"],
            "culinary": ["Croissants & Café in local bistro", "Crêpes & Galettes from street stands", "Coq au Vin traditional recipe", "French Macarons from specialty shop"],
            "tips": ["Buy a Paris Museum Pass to skip ticket lines.", "Use the Metro instead of expensive taxis.", "Book Louvre Museum tickets online early."]
        },
        "tokyo": {
            "attractions": ["Tokyo Tower", "Senso-ji Temple", "Shibuya Crossing", "Meiji Shrine", "Shinjuku Gyoen National Garden", "Tokyo Skytree"],
            "culinary": ["Fresh Sushi & Sashimi at Tsukiji", "Hot Ramen & Gyoza at a local stand", "Yakitori skewers or Tempura", "Matcha Parfait or Taiyaki waffle"],
            "tips": ["Get a Suica/Pasmo IC card for train travel.", "Keep cash handy as many places are cash-only.", "Rent pocket Wi-Fi at the airport for navigation."]
        },
        "new york": {
            "attractions": ["Statue of Liberty", "Central Park", "Empire State Building", "Times Square", "Metropolitan Museum of Art", "Brooklyn Bridge"],
            "culinary": ["NY Style Pizza slice", "Bagel with Lox & Cream Cheese", "Nathan's Hot Dog at Coney Island", "Classic New York Cheesecake"],
            "tips": ["Use the subway to bypass Manhattan traffic.", "Do not buy tickets from street solicitors.", "Use the TKTS booth for discounted Broadway shows."]
        },
        "delhi": {
            "attractions": ["Red Fort", "Qutub Minar", "Lotus Temple", "India Gate", "Humayun's Tomb", "Akshardham Temple"],
            "culinary": ["Rich Butter Chicken with Naan", "Chole Bhature local specialty", "Delicious Street Chaat", "Kulfi falooda dessert"],
            "tips": ["Use the Delhi Metro, it is fast and clean.", "Drink bottled mineral water exclusively.", "Dress conservatively when visiting religious sites."]
        },
        "london": {
            "attractions": ["Big Ben & Palace of Westminster", "London Eye", "Tower of London", "British Museum", "Buckingham Palace", "Tate Modern Gallery"],
            "culinary": ["Fish & Chips with Mushy Peas", "Full English Breakfast", "Classic Beef Wellington", "Scones with Clotted Cream & Tea"],
            "tips": ["Use Oyster card or contactless payment on transit.", "Most major museums offer free general admission.", "Always carry a small umbrella in your day pack."]
        },
        "rome": {
            "attractions": ["Colosseum", "Vatican Museums & Sistine Chapel", "Trevi Fountain", "Pantheon", "Roman Forum", "Spanish Steps"],
            "culinary": ["Pasta Carbonara or Cacio e Pepe", "Artisanal Italian Gelato", "Pizza al Taglio (pizza by the slice)", "Classic Espresso and Tiramisu"],
            "tips": ["Book Colosseum/Vatican tickets online weeks early.", "Fill water bottles at public fountains (nasoni) for free.", "Walk one block away from main squares for cheaper dining."]
        },
        "barcelona": {
            "attractions": ["Sagrada Família", "Park Güell", "Casa Batlló", "Las Ramblas", "Gothic Quarter walking tour", "Montjuïc Castle & Cable Car"],
            "culinary": ["Seafood Paella", "Assorted Tapas & Sangria", "Churros con Chocolate", "Pan con Tomate (tomato bread)"],
            "tips": ["Be highly vigilant against pickpockets on Las Ramblas.", "Book Sagrada Família and Park Güell tickets in advance.", "Purchase a T-casual transit card for 10 rides."]
        },
        "sydney": {
            "attractions": ["Sydney Opera House", "Sydney Harbour Bridge", "Bondi Beach", "Taronga Zoo", "Darling Harbour", "Royal Botanic Garden"],
            "culinary": ["Traditional Meat Pies", "Fresh grilled Barramundi", "Vegemite on Toast", "Pavlova dessert with fresh fruit"],
            "tips": ["Use Opal card for trains, buses, and ferries.", "Swim only between the red and yellow safety flags.", "Apply SPF 50+ sunscreen regularly throughout the day."]
        },
        "mumbai": {
            "attractions": ["Gateway of India", "Marine Drive", "Elephanta Caves", "Chhatrapati Shivaji Terminus", "Haji Ali Dargah", "Colaba Causeway market"],
            "culinary": ["Spicy Vada Pav street food", "Pav Bhaji with buttered rolls", "Bhel Puri or Sev Puri", "Bombay Cutting Chai"],
            "tips": ["Use local trains outside rush hour periods.", "Always insist on using taxi/auto meters.", "Enjoy street food at popular stalls with high turnover."]
        },
        "kyoto": {
            "attractions": ["Fushimi Inari Shrine", "Kinkaku-ji (Golden Pavilion)", "Arashiyama Bamboo Grove", "Kiyomizu-dera Temple", "Gion District", "Nijo Castle"],
            "culinary": ["Matcha Treats", "Yudofu (Tofu hot pot)", "Ramen", "Soba noodles"],
            "tips": ["Buy a Kyoto Bus/Subway pass.", "Respect local Geisha in Gion.", "Start very early to beat crowds."]
        }
    }
    
    city_details = None
    city_lower = destination.lower()
    for key, val in db.items():
        if key in city_lower:
            city_details = val
            break
            
    if not city_details:
        # Dynamic Wikipedia search fallback
        try:
            import requests
            from functools import partial
            # Monkeypatch requests to bypass SSL verification globally
            requests.get = partial(requests.get, verify=False)
            import wikipedia
            wikipedia.set_user_agent('AeroPlanTravelPlanner/1.0 (contact@aeroplan.com)')
            search_results = wikipedia.search(f"attractions in {destination}")
            attractions = []
            for res in search_results:
                if any(term in res.lower() for term in ["list of", "lists of", "tourism in", "outline of", "syndrome", "disney"]):
                    continue
                attractions.append(res)
                if len(attractions) >= 6:
                    break
            if len(attractions) < 3:
                search_results = wikipedia.search(f"{destination} landmarks")
                for res in search_results:
                    if res not in attractions and not any(term in res.lower() for term in ["list of", "lists of", "tourism in"]):
                        attractions.append(res)
                    if len(attractions) >= 6:
                        break
            if len(attractions) >= 3:
                city_details = {
                    "attractions": attractions,
                    "culinary": [f"Signature regional plate of {destination}", f"Famous local street food of {destination}", f"Traditional dessert unique to {destination}", f"Popular neighborhood café specialty"],
                    "tips": [f"Research local customs specific to {destination}.", f"Check local transit card options for {destination}.", f"Keep cash and cards handy as payment methods vary."]
                }
        except Exception:
            pass
            
    if not city_details:
        # Absolute template fallback
        city_details = {
            "attractions": [f"{destination} Historic Center", f"{destination} Scenic Park", f"{destination} Cultural Quarter", f"{destination} Museum of Art", f"{destination} Panoramic Lookout", f"{destination} Landmark Square"],
            "culinary": [f"Classic local meal in {destination}", f"Street food highlights of {destination}", f"Signature neighborhood delicacies", f"Popular local pastry / dessert"],
            "tips": [f"Learn a few basic phrases of the local language.", f"Use public transportation to get around {destination}.", f"Carry local cash for small purchases and tips."]
        }

    if "travel researcher" in system_content.lower():
        title = t["research_title"].format(destination=destination)
        interests_lbl = t["interests_label"].format(interests=interests)
        wiki_summary = get_city_attractions(destination)
        
        if is_kyoto and language in kyoto_localizations:
            k = kyoto_localizations[language]
            return f"""{title}
{interests_lbl}

{t["attractions_title"]}
{k["attractions"]}

{t["culinary_title"]}
{k["culinary"]}

{t["tips_title"]}
{k["tips"]}

### ☑️ Live Tourist Highlights (via Wikipedia)
{wiki_summary}
"""
        else:
            # Dynamically format list for any city
            attr_list = "\n".join(f"{i+1}. **{attr}**: Popular landmark in {destination}." for i, attr in enumerate(city_details["attractions"][:3]))
            culinary_list = "\n".join(f"- **{food}**" for food in city_details["culinary"][:3])
            tips_list = "\n".join(f"- **{tip}**" for tip in city_details["tips"][:3])
            return f"""{title}
{interests_lbl}

{t["attractions_title"]}
{attr_list}

{t["culinary_title"]}
{culinary_list}

{t["tips_title"]}
{tips_list}

### ☑️ Live Tourist Highlights (via Wikipedia)
{wiki_summary}
"""

    elif "budget manager" in system_content.lower():
        # Resolve cost averages via CITY_COST_PROFILES
        city_prof = None
        dest_lower = destination.lower()
        for city_key, prof in CITY_COST_PROFILES.items():
            if city_key in dest_lower:
                city_prof = prof
                break
                
        if city_prof:
            base_lodging = city_prof["lodging"]
            base_dining = city_prof["dining"]
            base_transit = city_prof["transit"]
            base_activities = city_prof["activities"]
        else:
            base_lodging = 90.0 if is_kyoto else 80.0
            base_dining = 40.0 if is_kyoto else 45.0
            base_transit = 10.0 if is_kyoto else 15.0
            base_activities = 15.0 if is_kyoto else 20.0
        base_misc = 10.0
        
        lodging = int(base_lodging * rate)
        dining = int(base_dining * rate)
        transit = int(base_transit * rate)
        activities = int(base_activities * rate)
        misc = int(base_misc * rate)
        
        daily_total = lodging + dining + transit + activities + misc
        total_est = daily_total * duration
        converted_limit = int(budget_limit)
        
        # Enforce minimum cost floors (Lodging: $20, Dining: $12)
        min_lodging_usd = 20.0
        min_dining_usd = 12.0
        min_transit_usd = 3.0
        min_activities_usd = 2.0
        min_misc_usd = 2.0
        
        # Scaling logic: if estimate exceeds limit, scale down base costs to fit strictly within budget
        if total_est > converted_limit:
            target_total = converted_limit * 0.95
            scale = target_total / total_est
            lodging = max(int(lodging * scale), int(min_lodging_usd * rate))
            dining = max(int(dining * scale), int(min_dining_usd * rate))
            transit = max(int(transit * scale), int(min_transit_usd * rate))
            activities = max(int(activities * scale), int(min_activities_usd * rate))
            misc = max(int(misc * scale), int(min_misc_usd * rate))
            
            daily_total = lodging + dining + transit + activities + misc
            total_est = daily_total * duration
            
        status_text = t["within_budget"] if total_est <= converted_limit else t["exceeds_budget"]
        
        # Warning alert if the selected budget is too tight
        min_survival_daily = min_lodging_usd + min_dining_usd + min_transit_usd
        min_survival_total = min_survival_daily * duration
        is_budget_too_tight = (budget_limit / rate) < min_survival_total
        
        warning_banner = ""
        warning_alerts = {
            "English": "⚠️ **Warning: Your budget is extremely tight for this destination!** We recommend increasing your budget to at least {sym}{min_budget} to cover baseline lodging and meals.",
            "Spanish": "⚠️ **Advertencia: ¡Su presupuesto es extremadamente ajustado para este destino!** Recomendamos aumentar su presupuesto a al menos {sym}{min_budget} para cubrir el alojamiento y las comidas básicas.",
            "Japanese": "⚠️ **警告：この目的地の予算が非常に厳しくなっています！** 基本的な宿泊費と食費をカバーするために、予算を少なくとも {sym}{min_budget} に増やすことをお勧めします。",
            "French": "⚠️ **Attention : Votre budget est extrêmement serré pour cette destination !** Nous vous recommandons d'augmenter votre budget à au moins {sym}{min_budget} pour couvrir l'hébergement et les repas de base.",
            "German": "⚠️ **Warnung: Ihr Budget ist für dieses Reiseziel extrem knapp!** Wir empfehlen, Ihr Budget auf mindestens {sym}{min_budget} zu erhöhen, um Unterkunft und Mahlzeiten zu decken.",
            "Hindi": "⚠️ **चेतावनी: इस गंतव्य के लिए आपका बजट बहुत कम है!** बुनियादी आवास और भोजन के खर्चों के लिए हम आपके बजट को कम से कम {sym}{min_budget} तक बढ़ाने की सलाह देते हैं।",
            "Telugu": "⚠️ **హెచ్చరిక: ఈ గమ్యస్థానానికి మీ బడ్జెట్ చాలా తక్కువగా ఉంది!** కనీస వసతి మరియు భోజన ఖర్చుల కోసం మీ బడ్జెట్‌ను కనీసం {sym}{min_budget} కి పెంచాల్సిందిగా సిఫార్సు చేస్తున్నాము."
        }
        
        if is_budget_too_tight:
            recommended_budget = int(min_survival_total * rate)
            warning_banner = warning_alerts.get(language, warning_alerts["English"]).format(sym=sym, min_budget=recommended_budget) + "\n\n"
            
        title = t["budget_title"].format(duration=duration, destination=destination)
        total_lbl = t["est_total"].format(sym=sym, total=total_est)
        limit_lbl = t["limit_label"].format(sym=sym, limit=converted_limit)
        status_lbl = t["status_label"].format(status=status_text)
        
        # Dynamic category details specific to city
        details_lodging = f"Ryokan/cozy hotel in {destination}" if is_kyoto else f"Standard hotel/guesthouse in {destination}"
        details_dining = f"Local specialties like {city_details['culinary'][0]}"
        details_transit = f"Public transit pass in {destination}"
        details_activities = f"Entry fees for {city_details['attractions'][0]}"
        details_misc = "Souvenirs and pocket money"
        
        categories = t["categories"]
        
        table = f"""{t["table_headers"].format(curr=currency)}
| :--- | :--- | :--- | :--- |
| **{categories["Accommodation"]}** | {sym}{lodging} | {sym}{lodging * duration} | {details_lodging} |
| **{categories["Dining & Drinks"]}** | {sym}{dining} | {sym}{dining * duration} | {details_dining} |
| **{categories["Transit"]}** | {sym}{transit} | {sym}{transit * duration} | {details_transit} |
| **{categories["Activities & Entry"]}** | {sym}{activities} | {sym}{activities * duration} | {details_activities} |
| **{categories["Miscellaneous"]}** | {sym}{misc} | {sym}{misc * duration} | {details_misc} |
| **{categories["Total"]}** | **{sym}{daily_total}** | **{sym}{total_est}** | **Ready for booking** |"""
        
        saving_tips = "\n".join(f"- {tip}" for tip in city_details["tips"])
        
        return f"""{warning_banner}{title}
{total_lbl}
{limit_lbl}
{status_lbl}

{table}

{t["saving_tips_title"]}
{saving_tips}
"""

    elif "itinerary planner" in system_content.lower():
        title = t["itinerary-title"] if "itinerary-title" in t else t["itinerary_title"]
        title_formatted = title.format(duration=duration, destination=destination)
        
        # Scale costs inside planner node as well to remain consistent using CITY_COST_PROFILES
        city_prof = None
        dest_lower = destination.lower()
        for city_key, prof in CITY_COST_PROFILES.items():
            if city_key in dest_lower:
                city_prof = prof
                break
                
        if city_prof:
            base_lodging = city_prof["lodging"]
            base_dining = city_prof["dining"]
            base_transit = city_prof["transit"]
            base_activities = city_prof["activities"]
        else:
            base_lodging = 90.0 if is_kyoto else 80.0
            base_dining = 40.0 if is_kyoto else 45.0
            base_transit = 10.0 if is_kyoto else 15.0
            base_activities = 15.0 if is_kyoto else 20.0
        base_misc = 10.0
        
        lodging = int(base_lodging * rate)
        dining = int(base_dining * rate)
        transit = int(base_transit * rate)
        activities = int(base_activities * rate)
        misc = int(base_misc * rate)
        
        daily_total = lodging + dining + transit + activities + misc
        total_est = daily_total * duration
        converted_limit = int(budget_limit)
        
        # Enforce minimum cost floors (Lodging: $20, Dining: $12)
        min_lodging_usd = 20.0
        min_dining_usd = 12.0
        min_transit_usd = 3.0
        min_activities_usd = 2.0
        min_misc_usd = 2.0
        
        if total_est > converted_limit:
            target_total = converted_limit * 0.95
            scale = target_total / total_est
            lodging = max(int(lodging * scale), int(min_lodging_usd * rate))
            dining = max(int(dining * scale), int(min_dining_usd * rate))
            transit = max(int(transit * scale), int(min_transit_usd * rate))
            activities = max(int(activities * scale), int(min_activities_usd * rate))
            misc = max(int(misc * scale), int(min_misc_usd * rate))
            daily_total = lodging + dining + transit + activities + misc
            total_est = daily_total * duration

        val_morning_act = int(activities * 0.4)
        val_afternoon_act = int(activities * 0.6)
        val_lunch = int(dining * 0.35)
        val_evening_din = int(dining * 0.65)
        
        # Warning alert if the selected budget is too tight
        min_survival_daily = min_lodging_usd + min_dining_usd + min_transit_usd
        min_survival_total = min_survival_daily * duration
        is_budget_too_tight = (budget_limit / rate) < min_survival_total
        
        warning_banner = ""
        warning_alerts = {
            "English": "⚠️ **Warning: Your budget is extremely tight for this destination!** We recommend increasing your budget to at least {sym}{min_budget} to cover baseline lodging and meals.",
            "Spanish": "⚠️ **Advertencia: ¡Su presupuesto es extremadamente ajustado para este destino!** Recomendamos aumentar su presupuesto a al menos {sym}{min_budget} para cubrir el alojamiento y las comidas básicas.",
            "Japanese": "⚠️ **警告：この目的地の予算が非常に厳しくなっています！** 基本的な宿泊費と食費をカバーするために、予算を少なくとも {sym}{min_budget} に増やすことをお勧めします。",
            "French": "⚠️ **Attention : Votre budget est extrêmement serré pour cette destination !** Nous vous recommandons d'augmenter votre budget à au moins {sym}{min_budget} pour couvrir l'hébergement et les repas de base.",
            "German": "⚠️ **Warnung: Ihr Budget ist für dieses Reiseziel extrem knapp!** Wir empfehlen, Ihr Budget auf mindestens {sym}{min_budget} zu erhöhen, um Unterkunft und Mahlzeiten zu decken.",
            "Hindi": "⚠️ **चेतावनी: इस गंतव्य के लिए आपका बजट बहुत कम है!** बुनियादी आवास और भोजन के खर्चों के लिए हम आपके बजट को कम से कम {sym}{min_budget} तक बढ़ाने की सलाह देते हैं।",
            "Telugu": "⚠️ **హెచ్చరిక: ఈ గమ్యస్థానానికి మీ బడ్జెట్ చాలా తక్కువగా ఉంది!** కనీస వసతి మరియు భోజన ఖర్చుల కోసం మీ బడ్జెట్‌ను కనీసం {sym}{min_budget} కి పెంచాల్సిందిగా సిఫార్సు చేస్తున్నాము."
        }
        
        if is_budget_too_tight:
            recommended_budget = int(min_survival_total * rate)
            warning_banner = warning_alerts.get(language, warning_alerts["English"]).format(sym=sym, min_budget=recommended_budget) + "\n\n"
        
        if is_kyoto and language in kyoto_localizations:
            k = kyoto_localizations[language]
            
            # Fetch fact-checked costs for Kyoto attractions
            cost_fushimi = get_fact_checked_activity_cost("Fushimi Inari Shrine", val_morning_act, sym, rate)
            cost_kinkaku = get_fact_checked_activity_cost("Kinkaku-ji", val_afternoon_act, sym, rate)
            cost_arashiyama = get_fact_checked_activity_cost("Arashiyama Bamboo Grove", val_morning_act, sym, rate)
            cost_kiyomizu = get_fact_checked_activity_cost("Kiyomizu-dera", val_morning_act, sym, rate)
            
            # Replace placeholder costs in the translated Kyoto plans
            day1_body = k["itinerary_day1"].replace("*(Est: $15)*", f"*(Est: {sym}{val_lunch})*").replace("*(Est: $5 entry)*", f"*(Est: {sym}{cost_fushimi} entry)*").replace("*(Est: $18)*", f"*(Est: {sym}{val_evening_din})*")
            day2_body = k["itinerary_day2"].replace("*(Est: $5 entry)*", f"*(Est: {sym}{cost_arashiyama} entry)*").replace("*(Est: $25)*", f"*(Est: {sym}{val_lunch})*").replace("*(Est: $10)*", f"*(Est: {sym}{val_afternoon_act})*").replace("*(Est: $30)*", f"*(Est: {sym}{val_evening_din})*")
            day3_body = k["itinerary_day3"].replace("*(Est: $4 entry)*", f"*(Est: {sym}{cost_kiyomizu} entry)*").replace("*(Est: $12)*", f"*(Est: {sym}{val_lunch})*").replace("*(Est: $10)*", f"*(Est: {sym}{val_afternoon_act})*").replace("*(Est: $25)*", f"*(Est: {sym}{val_evening_din})*")
            
            day1_title = t["day_label"].format(d=1) + ": " + k.get("day1_title", "Historic Temples & Street Food")
            day2_title = t["day_label"].format(d=2) + ": " + k.get("day2_title", "Bamboo Groves & Tea Culture")
            day3_title = t["day_label"].format(d=3) + ": " + k.get("day3_title", "Panoramic Views & Traditional Walks")
            
            # Fetch directions
            directions_day1 = ""
            instructions_day1 = get_clean_directions("Kyoto Station", "Fushimi Inari Shrine, Kyoto", language)
            if instructions_day1:
                directions_day1 = "\n\n**🚗 Driving Directions (Kyoto Station to Fushimi Inari Shrine):**\n" + "\n".join(f"- {inst}" for inst in instructions_day1[:3])
            day1_body += directions_day1

            directions_day2 = ""
            instructions_day2 = get_clean_directions("Kyoto Station", "Arashiyama Bamboo Grove, Kyoto", language)
            if instructions_day2:
                directions_day2 = "\n\n**🚗 Driving Directions (Kyoto Station to Arashiyama Bamboo Grove):**\n" + "\n".join(f"- {inst}" for inst in instructions_day2[:3])
            day2_body += directions_day2

            directions_day3 = ""
            instructions_day3 = get_clean_directions("Fushimi Inari Shrine, Kyoto", "Kiyomizu-dera, Kyoto", language)
            if instructions_day3:
                directions_day3 = "\n\n**🚗 Driving Directions (Fushimi Inari to Kiyomizu-dera):**\n" + "\n".join(f"- {inst}" for inst in instructions_day3[:3])
            day3_body += directions_day3
            
            return f"""{warning_banner}{title_formatted}

---

#### {day1_title}
{day1_body}

#### {day2_title}
{day2_body}

#### {day3_title}
{day3_body}

---

{t["checklist_title"]}
{k["checklist"]}
"""
        else:
            day_plans = []
            attractions = city_details["attractions"]
            culinary = city_details["culinary"]
            
            for d in range(1, duration + 1):
                # Cycle attractions/foods to make every day unique
                morning_spot = attractions[(d*2 - 2) % len(attractions)]
                afternoon_spot = attractions[(d*2 - 1) % len(attractions)]
                evening_spot = attractions[(d*2) % len(attractions)]
                lunch_food = culinary[(d - 1) % len(culinary)]
                evening_food = culinary[d % len(culinary)]
                
                # Fetch fact-checked costs for attractions
                cost_morning = get_fact_checked_activity_cost(morning_spot, val_morning_act, sym, rate)
                cost_afternoon = get_fact_checked_activity_cost(afternoon_spot, val_afternoon_act, sym, rate)
                
                # Fetch localized text items
                localized_items = get_itinerary_day_template(
                    language, morning_spot, lunch_food, afternoon_spot, evening_spot, evening_food,
                    sym, cost_morning, val_lunch, cost_afternoon, val_evening_din
                )
                
                day_title_prefix = t["day_label"].format(d=d)
                day_title_suffix = "Exploración" if language == "Spanish" else "観光名所巡り" if language == "Japanese" else "Exploration" if language == "French" else "Erkundung" if language == "German" else "भ्रमण और दर्शनीय स्थल" if language == "Hindi" else "సందర్శన" if language == "Telugu" else "Sightseeing"
                day_title = f"{day_title_prefix}: {day_title_suffix} - {morning_spot} & {afternoon_spot}"
                
                directions_gen = ""
                if d == 1 and len(attractions) >= 2:
                    instructions_gen = get_clean_directions(f"{destination} Airport", f"{morning_spot}, {destination}", language)
                    if instructions_gen:
                        directions_gen = f"\n\n**🚗 Driving Directions (Airport to {morning_spot}):**\n" + "\n".join(f"- {inst}" for inst in instructions_gen[:3])
                
                day_plans.append(f"""#### {day_title}
{localized_items['morning']}
{localized_items['lunch']}
{localized_items['afternoon']}
{localized_items['evening']}{directions_gen}""")
                
            day_plans_str = "\n\n".join(day_plans)
            
            checklist_desc = "- [ ] Descargar pases de transporte local.\n- [ ] Reservar entradas de tours matutinos.\n- [ ] Descargar mapas sin conexión.\n- [ ] Llevar adaptador de enchufe local." if language == "Spanish" else \
                             "- [ ] 交通系パスをダウンロードする。\n- [ ] 午前中の現地ツアーを予約する。\n- [ ] オフラインマップを用意する。\n- [ ] 電源変換アダプターを確認する。" if language == "Japanese" else \
                             "- [ ] Télécharger les pass de transport locaux.\n- [ ] Réserver les entrées des visites matinales.\n- [ ] Télécharger les cartes hors ligne.\n- [ ] Emporter un adaptateur de prise local." if language == "French" else \
                             "- [ ] Lokale ÖPNV-Tickets herunterladen.\n- [ ] Reservierung für Morgen-Führungen sichern.\n- [ ] Offline-Kartenmaterial herunterladen.\n- [ ] Reiseadapter einpacken." if language == "German" else \
                             "- [ ] स्थानीय यातायात पास डाउनलोड करें।\n- [ ] सुबह की यात्राएं बुक करें।\n- [ ] ऑफ़लाइन मानचित्र सहेजें।\n- [ ] यात्रा प्लग कनवर्टर साथ रखें।" if language == "Hindi" else \
                             "- [ ] స్థానిక రవాణా పాస్ పొందండి.\n- [ ] ఉదయపు పర్యటనలు బుక్ చేసుకోండి.\n- [ ] ఆఫ్ లైన్ మ్యాప్స్ డౌన్ లోడ్ చేయండి.\n- [ ] లోకల్ ప్లగ్ అడాప్టర్ సిద్ధం చేసుకోండి." if language == "Telugu" else \
                             "- [ ] Download local transit passes.\n- [ ] Book tickets for morning excursions.\n- [ ] Save offline map guides.\n- [ ] Pack local socket plug adapter."
                             
            return f"""{warning_banner}{title_formatted}

---

{day_plans_str}

---

{t["checklist_title"]}
{checklist_desc}
"""

    return AIMessage(content="Simulated Response")



# 9. Build LangGraph Workflow
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("researcher", researcher_agent)
workflow.add_node("budget", budget_agent)
workflow.add_node("planner", itinerary_planner_agent)

# Add routing logic (conditional edges)
workflow.add_conditional_edges(
    START,
    route_next,
    {
        "researcher": "researcher",
        "budget": "budget",
        "planner": "planner",
        END: END
    }
)

workflow.add_conditional_edges(
    "researcher",
    route_next,
    {
        "researcher": "researcher",
        "budget": "budget",
        "planner": "planner",
        END: END
    }
)

workflow.add_conditional_edges(
    "budget",
    route_next,
    {
        "researcher": "researcher",
        "budget": "budget",
        "planner": "planner",
        END: END
    }
)

workflow.add_conditional_edges(
    "planner",
    route_next,
    {
        "researcher": "researcher",
        "budget": "budget",
        "planner": "planner",
        END: END
    }
)

# Compile
app = workflow.compile()

