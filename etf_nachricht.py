import datetime
import json
import os
import requests
import yfinance as yf

NTFY_TOPIC = "hans-etf-xk92mq"  # dein eigenes, schwer zu erratendes Thema

ETFS = {
    "XDWD.DE": {"anteil_prozent": 0.50, "name": "World"},
    "XMME.DE": {"anteil_prozent": 0.30, "name": "EM"},
    "XSX6.DE": {"anteil_prozent": 0.20, "name": "Europe"},
}
MONATLICHE_RATE = 300.0

STATE_DATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "etf_state.json")

STARTWERTE = {
    "anteile": {
        "XDWD.DE": 3.1072,
        "XMME.DE": 3.2236,
        "XSX6.DE": 1.0236,
    },
    "eingezahlt": 1149.97,
    "letzter_verarbeiteter_monat": "2026-08",
}


def lade_zustand():
    if os.path.exists(STATE_DATEI):
        with open(STATE_DATEI, "r") as f:
            return json.load(f)
    return dict(STARTWERTE)


def speichere_zustand(zustand):
    with open(STATE_DATEI, "w") as f:
        json.dump(zustand, f, indent=2)


def naechster_handelstag(datum):
    while datum.weekday() >= 5:
        datum += datetime.timedelta(days=1)
    return datum


def ausfuehrungstag(jahr, monat):
    tag = datetime.date(jahr, monat, 20)
    return naechster_handelstag(tag)


def hole_eroeffnungskurs(ticker, datum):
    t = yf.Ticker(ticker)
    hist = t.history(start=datum.isoformat(), end=(datum + datetime.timedelta(days=1)).isoformat())
    if hist.empty:
        return None
    return float(hist["Open"].iloc[0])


def hole_aktuellen_kurs(ticker):
    t = yf.Ticker(ticker)
    try:
        info = t.fast_info
        waehrung = info.get("currency", "unbekannt")
        preis = info.get("lastPrice")
        print(f"{ticker} fast_info: Preis={preis}, Waehrung={waehrung}")
        if preis:
            return float(preis)
    except Exception as e:
        print(f"{ticker}: fast_info fehlgeschlagen: {e}")

    hist = t.history(period="5d")
    if hist.empty:
        print(f"{ticker}: auch history() liefert nichts")
        return None
    print(f"{ticker} letzte 5 Handelstage:\n{hist[['Close']].to_string()}")
    return float(hist["Close"].iloc[-1])


def pruefe_monatlichen_kauf(zustand):
    heute = datetime.date.today()
    dieser_monat = f"{heute.year}-{heute.month:02d}"
    if zustand["letzter_verarbeiteter_monat"] == dieser_monat:
        return
    tag = ausfuehrungstag(heute.year, heute.month)
    if heute < tag:
        return
    for ticker, info in ETFS.items():
        betrag = MONATLICHE_RATE * info["anteil_prozent"]
        kurs = hole_eroeffnungskurs(ticker, tag)
        if kurs is None:
            return
        zustand["anteile"][ticker] += betrag / kurs
    zustand["eingezahlt"] += MONATLICHE_RATE
    zustand["letzter_verarbeiteter_monat"] = dieser_monat


def berechne_werte(zustand):
    einzelwerte = {}
    gesamtwert = 0.0
    for ticker, info in ETFS.items():
        kurs = hole_aktuellen_kurs(ticker)
        if kurs is None:
            return None, None, None
        wert = zustand["anteile"][ticker] * kurs
        einzelwerte[info["name"]] = wert
        gesamtwert += wert
    eingezahlt = zustand["eingezahlt"]
    rendite = ((gesamtwert - eingezahlt) / eingezahlt) * 100 if eingezahlt > 0 else 0.0
    return gesamtwert, rendite, einzelwerte


def sende_ntfy(nachricht):
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=nachricht.encode("utf-8"))


def main():
    zustand = lade_zustand()
    pruefe_monatlichen_kauf(zustand)

    gesamtwert, rendite, einzelwerte = berechne_werte(zustand)
    if gesamtwert is None:
        print("Kursabruf fehlgeschlagen, keine Nachricht gesendet.")
        return

    vorzeichen = "+" if rendite >= 0 else ""
    teile = " | ".join(f"{name}: {wert:.0f}EUR" for name, wert in einzelwerte.items())
    nachricht = f"ETF-Sparplan: {gesamtwert:.2f}EUR ({vorzeichen}{rendite:.2f}%) -- {teile}"

    print(nachricht)
    sende_ntfy(nachricht)
    speichere_zustand(zustand)


if __name__ == "__main__":
    main()
