import pandas as pd
from pm4py.objects.ocel.importer import csv as ocel_csv_importer  # optional, for validation if needed

# Pfade und Dateinamen (ggf. anpassen)
input_csv_path =  r"C:\Users\vince\PycharmProjects\OCELConverter\input\input.csv"
output_json_path = r"C:\Users\vince\PycharmProjects\OCELConverter\output\events_ocel.json"
output_log_path = r"C:\Users\vince\PycharmProjects\OCELConverter\output\output_log.txt"

# 1. CSV-Datei einlesen
df = pd.read_csv(input_csv_path)

# 2. Identifikation der relevanten Spalten
time_cols = [col for col in df.columns if "time" in col.lower()]      # z.B. ['starttime','completiontime']
ref_cols = [col for col in df.columns if col.startswith("ref_")]      # Objekt-Referenzen
# Wähle 'completiontime' oder letzte Zeitspalte als Haupt-Timestamp (Fallback zu erster wenn nicht vorhanden)
if "completiontime" in [c.lower() for c in time_cols]:
    timestamp_col = [c for c in time_cols if c.lower() == "completiontime"][0]
elif time_cols:
    timestamp_col = time_cols[-1]
else:
    raise Exception("Keine Zeitstempel-Spalte gefunden.")
# Event-Attribut-Spalten: alle ohne Zeit/Objekt-Prefix und ohne explizite Event-ID-Spalte
event_id_col = None
if "eventid" in df.columns:
    event_id_col = "eventid"
event_attr_cols = []
for col in df.columns:
    if col == event_id_col or col == timestamp_col or col in time_cols:
        continue  # überspringe Event-ID und Zeitspalten
    if col in ref_cols:
        continue  # überspringe Objekt-Referenzspalten
    event_attr_cols.append(col)

# 3. Konvertiere Zeitstempel-Spalte zu datetime und anschließend zu ISO-Format-Strings
df[timestamp_col] = pd.to_datetime(df[timestamp_col])
# Umwandlung in ISO 8601 String (mit Zulu-Zeitzone falls UTC, sonst Offset)
df[timestamp_col] = df[timestamp_col].apply(lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%S") + (dt.strftime("%z") or ""))
# Hinweis: strftime("%z") gibt z.B. +0100; für 'Z' bei UTC könnte man alternativ prüfen und 'Z' anhängen.

# 4. Erzeuge Datenstrukturen für Events und Objekte
events = {}
objects = {}
obj_types_set = set()
event_types_set = set()

# Objekt-ID Mapping (für Eindeutigkeit, falls nötig)
object_id_map = {}  # Schlüssel: (obj_type, original_id) -> eindeutiger Objekt-Key
obj_type_counters = {}

for idx, row in df.iterrows():
    # Bestimme Event-ID (als Schlüssel in der OCEL Events-Dict)
    if event_id_col:
        event_id = str(row[event_id_col])
    else:
        # Falls keine eventid-Spalte vorhanden, generiere einen fortlaufenden Key
        event_id = f"e{idx+1}"
    # Event-Aktivität und Zeitstempel
    activity = str(row["activity"]) if "activity" in df.columns else "UndefinedActivity"
    timestamp = str(row[timestamp_col])
    event_types_set.add(activity)
    # Objektzuordnungen (omap) für dieses Event sammeln
    omap_list = []
    for ref_col in ref_cols:
        obj_val = row[ref_col]
        if pd.isna(obj_val) or obj_val == "" or obj_val is None:
            continue  # kein Objekt in diesem Event für diesen Typ
        obj_val = str(obj_val)
        obj_type = ref_col.replace("ref_", "")
        obj_types_set.add(obj_type)
        # Baue eindeutigen Objekt-Key
        obj_key = obj_val
        # Falls die Objekt-ID schon für einen anderen Typ vorkam oder Typ kommt mehrfach, füge Typ-Präfix hinzu
        obj_id_tuple = (obj_type, obj_val)
        if obj_id_tuple in object_id_map:
            obj_key = object_id_map[obj_id_tuple]
        else:
            # Generiere neuen Objekt-Key
            # Beispiel: "customer_123" für obj_type "customer" und ID "123"
            new_obj_key = f"{obj_type}_{obj_val}" if obj_val not in objects else obj_val
            # Falls der Schlüssel noch existiert (Kollision), hänge Zähler an
            ctr = 2
            temp_key = new_obj_key
            while temp_key in objects:
                temp_key = f"{new_obj_key}_{ctr}"
                ctr += 1
            new_obj_key = temp_key
            object_id_map[obj_id_tuple] = new_obj_key
            obj_key = new_obj_key
            # Objekt in Objekte-Dict eintragen
            objects[obj_key] = {
                "ocel:type": obj_type,
                "ocel:ovmap": {}
            }
        # Zum Event-Objekt-Mapping hinzufügen
        omap_list.append(obj_key)
    # Event-Attribute (vmap) sammeln
    vmap_attrs = {}
    for attr in event_attr_cols:
        # Event-spezifisches Attribut
        # Event-spezifisches Attribut
        value = row[attr]
        if pd.isna(value):
            continue  # Attribut nicht gesetzt
        if isinstance(value, pd.Timestamp):
            continue  # Zeitwert, nicht aufnehmen

        # numpy-Typen in native Python-Typ umwandeln
        if hasattr(value, "item"):
            try:
                value = value.item()
            except:
                value = str(value)
        # Wert zur Attributliste hinzufügen
        vmap_attrs[str(attr)] = value
    # Event in Events-Dict ablegen
    events[event_id] = {
        "ocel:activity": activity,
        "ocel:timestamp": timestamp,
        "ocel:omap": omap_list,
        "ocel:vmap": vmap_attrs
    }

# 5. Globale Informationen für OCEL
attribute_names = sorted({attr for attr in event_attr_cols})  # Menge aller Event-Attributnamen
object_types = sorted(obj_types_set)
# (Event ID als Attribut wird nicht aufgeführt, da es als Schlüssel benutzt wurde und kein vmap-Attribut ist.)

# 6. Zusammenbauen der OCEL-Struktur als Dictionary
ocel_dict = {
    "ocel:global-log": {
        "ocel:attribute-names": attribute_names,
        "ocel:object-types": object_types,
        "ocel:version": "1.0",
        "ocel:ordering": "timestamp"
    },
    "ocel:global-event": {
        "ocel:activity": "__INVALID__",
        "ocel:timestamp": "__INVALID__",
        "ocel:omap": "__INVALID__",
        "ocel:vmap": "__INVALID__"
    },
    "ocel:global-object": {
        "ocel:type": "__INVALID__",
        "ocel:ovmap": "__INVALID__"
    },
    "ocel:events": events,
    "ocel:objects": objects
}

# 7. Als JSON-OCEL-Datei abspeichern
import json
with open(output_json_path, "w", encoding="utf-8") as f:
    json.dump(ocel_dict, f, ensure_ascii=False, indent=4)

# 8. Log-Datei mit Statistiken erstellen
num_events = len(events)
num_objects = len(objects)
num_event_types = len(event_types_set)
# EO-Relationen: Summe aller Zuordnungen (Anzahl Einträge in allen omap-Listen)
eo_relations = sum(len(evt["ocel:omap"]) for evt in events.values())
# OO-Relationen: Anzahl eindeutiger Objekt-Objekt-Paare, die zusammen in einem Event vorkommen
oo_pairs = set()
for evt in events.values():
    objs = evt["ocel:omap"]
    # Alle Kombinationen von 2 Objekten (ungeordnete Paare) aus diesem Event
    for i in range(len(objs)):
        for j in range(i+1, len(objs)):
            pair = tuple(sorted([objs[i], objs[j]]))
            oo_pairs.add(pair)
num_oo_relations = len(oo_pairs)
log_lines = [
    f"Events: {num_events}",
    f"Objects: {num_objects}",
    f"Event types: {num_event_types}",
    f"Event-object relations (EO): {eo_relations}",
    f"Object-object relations (OO): {num_oo_relations}"
]
with open(output_log_path, "w", encoding="utf-8") as f:
    f.write("\n".join(log_lines))

# Optional: Validierung der erzeugten OCEL durch erneuten Import mit PM4Py (OCEL-Importer)
try:
    _ = ocel_csv_importer.apply(output_json_path)
    print("OCEL file validated successfully by PM4Py.")
except Exception as e:
    print("Validation warning:", e)
