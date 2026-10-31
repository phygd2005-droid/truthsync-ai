"""Saving and reading verification reports."""
import json

from db import audit, notify, now


def save_verification(c, user_id, input_type, content, rep, source_url=None):
    cur = c.execute(
        "INSERT INTO verifications(user_id, input_type, content, source_url, verdict, basis,"
        " confidence, method, reason, claims_json, evidence_json, limitations_json,"
        " retrieved_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (user_id, input_type, content[:5000], source_url or rep.get("source_url"),
         rep["verdict"], rep.get("basis"), rep.get("confidence"), rep.get("method"),
         rep.get("reason"), json.dumps(rep.get("claims", [])),
         json.dumps({"supporting": rep.get("supporting", []),
                     "contradicting": rep.get("contradicting", []),
                     "related": rep.get("related", [])}),
         json.dumps(rep.get("limitations", [])), rep.get("retrieved_at"), now()))
    vid = cur.lastrowid
    c.execute("UPDATE verifications SET report_id=? WHERE id=?", (f"TS-{1000 + vid}", vid))
    notify(c, user_id, "verification", f"Report TS-{1000 + vid} completed: {rep['verdict']}.")
    audit(c, user_id, "verification", f"TS-{1000 + vid} {input_type} {rep['verdict']}")
    return vid


def get_report(c, user_id, vid):
    r = c.execute("SELECT * FROM verifications WHERE id=? AND user_id=?", (vid, user_id)).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["claims"] = json.loads(d.pop("claims_json") or "[]")
    d["evidence"] = json.loads(d.pop("evidence_json") or "{}")
    d["limitations"] = json.loads(d.pop("limitations_json") or "[]")
    return d
