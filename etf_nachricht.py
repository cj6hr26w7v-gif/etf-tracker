import datetime
import json
import os
import requests
import yfinance as yf

# -----------------------------
# Einstellungen
# -----------------------------

NTFY_TOPIC = "hans-etf-xk92mq"

ETFS = {
    "XDWD.DE": {"anteil_prozent": 0.50, "name": "World"},
    "XMME.DE": {"anteil_prozent": 0.30, "name": "EM"},
    "XSX6.DE": {"anteil_prozent": 0.20, "name": "Europe"},
}

MONATLICHE_RATE = 300.0

STATE_DATEI = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "etf_state.json"
)

STARTWERTE = {
    "anteile": {
        "XDWD.DE": 3.1072,
        "XMME.DE": 3.2236,
        "XSX6.DE": 1.0236
    },
    "eingezahlt": {
        "XDWD.DE": 424.985,
        "XMME.DE": 254.991,
        "XSX6.DE": 169.994
    },
    "letzter_verarbeiteter_monat": "2026-08"
}


# -----------------------------
# Zustand
# -----------------------------

def lade_zustand():
    if os.path.exists(STATE_DATEI):
        with open(STATE_DATEI, "r") as f:
            return json.load(f)
    return json.loads(json.dumps(STARTWERTE))


def speichere_zustand(zustand):
    with open(STATE_DATEI, "w") as f:
        json.dump(zustand, f, indent=2)


# -----------------------------
# Börsenfunktionen
# -----------------------------

def naechster_handelstag(datum):
    while datum.weekday() >= 5:
        datum += datetime.timedelta(days=1)
    return datum


def ausfuehrungstag(jahr, monat):
    return naechster_handelstag(datetime.date(jahr, monat, 20))


def hole_eroeffnungskurs(ticker, datum):
    t = yf.Ticker(ticker)
    hist = t.history(
        start=datum.isoformat(),
        end=(datum + datetime.timedelta(days=1)).isoformat()
    )

    if hist.empty:
        return None

    return float(hist["Open"].iloc[0])


def hole_aktuellen_kurs(ticker):
    t = yf.Ticker(ticker)

    try:
        preis = t.fast_info.get("lastPrice")
        if preis:
            return float(preis)
    except Exception:
        pass

    hist = t.history(period="5d")

    if hist.empty:
        return None

    return float(hist["Close"].iloc[-1])


def hole_tagesrichtung(ticker):
    t = yf.Ticker(ticker)
    hist = t.history(period="2d")

    if len(hist) < 2:
        return "→"

    gestern = float(hist["Close"].iloc[-2])
    heute = float(hist["Close"].iloc[-1])

    if heute > gestern:
        return "↑"
    elif heute < gestern:
        return "↓"
    else:
        return "→"


# -----------------------------
# Sparplan
# -----------------------------

def pruefe_monatlichen_kauf(zustand):
    heute = datetime.date.today()
    dieser_monat = f"{heute.year}-{heute.month:02d}"

    if zustand["letzter_verarbeiteter_monat"] == dieser_monat:
        return

    kaufdatum = ausfuehrungstag(heute.year, heute.month)

    if heute < kaufdatum:
        return

    for ticker, info in ETFS.items():
        betrag = MONATLICHE_RATE * info["anteil_prozent"]
        kurs = hole_eroeffnungskurs(ticker, kaufdatum)

        if kurs is None:
            return

        zustand["anteile"][ticker] += betrag / kurs
        zustand["eingezahlt"][ticker] += betrag

    zustand["letzter_verarbeiteter_monat"] = dieser_monat


# -----------------------------
# Depot berechnen
# -----------------------------

def berechne_werte(zustand):
    einzelwerte = {}
    gesamtwert = 0
    gesamt_eingezahlt = 0

    for ticker, info in ETFS.items():
        kurs = hole_aktuellen_kurs(ticker)

        if kurs is None:
            return None, None, None

        wert = zustand["anteile"][ticker] * kurs
        eingezahlt = zustand["eingezahlt"][ticker]

        rendite = (
            ((wert - eingezahlt) / eingezahlt) * 100
            if eingezahlt > 0 else 0
        )

        einzelwerte[info["name"]] = {
            "wert": wert,
            "rendite": rendite,
            "richtung": hole_tagesrichtung(ticker)
        }

        gesamtwert += wert
        gesamt_eingezahlt += eingezahlt

    gesamtrendite = (
        ((gesamtwert - gesamt_eingezahlt) / gesamt_eingezahlt) * 100
        if gesamt_eingezahlt > 0 else 0
    )

    return gesamtwert, gesamtrendite, einzelwerte


# -----------------------------
# Nachricht senden
# -----------------------------

def sende_ntfy(text):
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=text.encode("utf-8")
    )


# -----------------------------
# Hauptprogramm
# -----------------------------

def main():
    zustand = lade_zustand()

    pruefe_monatlichen_kauf(zustand)

    gesamtwert, gesamtrendite, einzelwerte = berechne_werte(zustand)

    if gesamtwert is None:
        print("Kursabruf fehlgeschlagen.")
        return

    vz = "+" if gesamtrendite >= 0 else ""

    teile = []

    reihenfolge = ["World", "EM", "Europe"]

    for name in reihenfolge:
        daten = einzelwerte[name]
        vz_etf = "+" if daten["rendite"] >= 0 else ""

        teile.append(
            f"{name} {daten['wert']:.0f}€ "
            f"({vz_etf}{daten['rendite']:.1f}%) "
            f"{daten['richtung']}"
        )

    nachricht = (
        f"{gesamtwert:.2f}€ ({vz}{gesamtrendite:.2f}%)\n\n"
        + " · ".join(teile)
    )

    print(nachricht)

    sende_ntfy(nachricht)

    speichere_zustand(zustand)


if __name__ == "__main__":
    main()
