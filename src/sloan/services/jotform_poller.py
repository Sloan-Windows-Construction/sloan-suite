import os, time, uuid, shutil, traceback
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import threading, requests

from ..config import DATE_FMT_DEFAULT, load_config, save_config
from ..utils.sanitize import sanitize_name

JF_BASE = "https://api.jotform.com"

def _safe_date(fmt: str) -> str:
    try:
        return datetime.now(timezone.utc).strftime(fmt)
    except Exception:
        return datetime.utcnow().strftime(DATE_FMT_DEFAULT)

def _ensure_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)

def _extract_customer(sub: Dict) -> str:
    answers = sub.get("answers") or {}
    # prefer proper name controls
    for v in answers.values():
        if not isinstance(v, dict):
            continue
        t = (v.get("type") or "").lower()
        txt = (v.get("text") or "").lower()
        ans = v.get("answer")
        if t in ("control_fullname", "control_name") or "name" in txt:
            if isinstance(ans, dict):
                fn = (ans.get("first") or "").strip()
                ln = (ans.get("last") or "").strip()
                full = f"{fn} {ln}".strip()
                if full:
                    return sanitize_name(full)
            if isinstance(ans, str) and ans.strip():
                # avoid accidentally getting JSON in a string
                if ans.strip().startswith("{") or ans.strip().startswith("["):
                    continue
                return sanitize_name(ans)
    # fallback: pick a plausible two+ word string (not an email, not huge)
    for v in answers.values():
        if isinstance(v, dict):
            a = v.get("answer")
            if isinstance(a, str) and "@" not in a and len(a.split()) >= 2 and len(a) <= 80:
                if a.strip().startswith("{") or a.strip().startswith("["):
                    continue
                return sanitize_name(a)
    return "Unknown Customer"

def _extract_files(sub: Dict) -> List[Tuple[str, str]]:
    """Return list of (name, url) tuples for uploaded files in the submission."""
    out: List[Tuple[str, str]] = []
    answers = sub.get("answers") or {}
    for v in answers.values():
        if not isinstance(v, dict):
            continue
        ans = v.get("answer")
        # List of dicts
        if isinstance(ans, list):
            for item in ans:
                if isinstance(item, dict) and item.get("url"):
                    name = item.get("name") or item.get("filename") or os.path.basename(item["url"].split("?")[0])
                    out.append((name, item["url"]))
                elif isinstance(item, str):
                    out.append((os.path.basename(item.split("?")[0]), item))
        # Single dict
        elif isinstance(ans, dict) and ans.get("url"):
            name = ans.get("name") or ans.get("filename") or os.path.basename(ans["url"].split("?")[0])
            out.append((name, ans["url"]))
        # Single string with url(s)
        elif isinstance(ans, str) and ans.startswith("http"):
            # Sometimes multiple URLs are comma-separated
            for u in [s.strip() for s in ans.split(",") if s.strip()]:
                out.append((os.path.basename(u.split("?")[0]), u))
    return out

class JotformPoller(threading.Thread):
    """
    Polls Jotform for new submissions for two forms (Measure Sheet, Completion Form),
    downloads file uploads + the generated submission PDF, and either:
      - uploads to SharePoint Downloads (stage_to_sharepoint=True), or
      - drops into local watch folder (stage_to_sharepoint=False)
    Names files per spec: {Customer} InitialP|FinalP {index} {Date}.{ext}
    """
    def __init__(self, cfg: Dict, graph_client, stop_evt: threading.Event, log_fn):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.graph = graph_client
        self.stop_evt = stop_evt
        self.log = log_fn

    def run(self):
        jf = self.cfg.get("jotform", {}) or {}
        if not jf.get("enabled"):
            self.log("[JOTFORM] Disabled"); return
        api_key = jf.get("api_key")
        if not api_key:
            self.log("[JOTFORM] No API key configured"); return

        poll_s = int(jf.get("poll_seconds", jf.get("poll_seconds", 180)))
        measure_id = jf.get("measure_sheet_form_id")
        completion_id = jf.get("completion_form_id")
        stage_spo = bool(jf.get("stage_to_sharepoint", True))

        if not (measure_id or completion_id):
            self.log("[JOTFORM] No form IDs configured"); return

        cursors: Dict[str, str] = (jf.get("cursors") or {}).copy()

        sess = requests.Session()
        sess.headers.update({"User-Agent": "SloanSuite/1.0"})
        sess.params = {"apiKey": api_key}

        limit = 50

        while not self.stop_evt.is_set():
            try:
                for form_id, kind in ((measure_id, "InitialP"), (completion_id, "FinalP")):
                    if not form_id:
                        continue

                    last_id = cursors.get(form_id, "")
                    offset = 0
                    newest_id_this_round: Optional[str] = None
                    index_counter = 0  # numbering within each submission

                    while not self.stop_evt.is_set():
                        url = f"{JF_BASE}/form/{form_id}/submissions"
                        params = {
                            "limit": limit,
                            "offset": offset,
                            "orderby": "created_at",  # ascending
                        }
                        r = sess.get(url, params=params, timeout=30)
                        if r.status_code != 200:
                            self.log(f"[JOTFORM] Fetch failed {r.status_code} {r.text}")
                            break

                        payload = r.json() or {}
                        items = payload.get("content") or []
                        if not items:
                            break

                        for sub in items:
                            sid = str(sub.get("id") or "")
                            if not sid:
                                continue
                            # Skip if we have already processed this id
                            if last_id and sid <= last_id:
                                continue

                            # Track newest id we see in this loop
                            if not newest_id_this_round or sid > newest_id_this_round:
                                newest_id_this_round = sid

                            customer = _extract_customer(sub)
                            date_str = _safe_date(self.cfg.get("date_format", DATE_FMT_DEFAULT))

                            # 1) Download uploaded files
                            files = _extract_files(sub)
                            for idx, (fname, url_download) in enumerate(files, start=1):
                                index_counter = idx
                                local_tmp = os.path.join(os.path.expanduser("~/.sloan_suite"),
                                                         f"jtf_{uuid.uuid4().hex}_{os.path.basename(fname)}")
                                with sess.get(url_download, stream=True, timeout=60) as resp:
                                    resp.raise_for_status()
                                    _ensure_dir(local_tmp)
                                    with open(local_tmp, "wb") as out:
                                        shutil.copyfileobj(resp.raw, out)

                                ext = os.path.splitext(local_tmp)[1]
                                clean_customer = sanitize_name(customer)
                                clean_kind = sanitize_name(kind)
                                clean_idx = sanitize_name(str(idx))
                                clean_date = sanitize_name(date_str)

                                new_name = sanitize_name(
                                    f"{clean_customer} {clean_kind} {clean_idx} {clean_date}") + ext

                                if stage_spo:
                                    dl = self.cfg.get("organizer", {}).get("downloads_folder_path", "/Downloads").strip(
                                        "/")
                                    sp_path = f"{dl}/{new_name}"  # e.g., 'Downloads/John Doe InitialP 1 2025-10-03.jpg'
                                    self.graph.upload_small(sp_path, local_tmp)
                                    try: os.remove(local_tmp)
                                    except Exception: pass
                                else:
                                    dest = os.path.join(self.cfg.get("watch_folder", os.path.expanduser("~")), new_name)
                                    _ensure_dir(dest)
                                    shutil.move(local_tmp, dest)

                            # 2) Download the generated PDF for the submission
                            try:
                                pdf_url = f"{JF_BASE}/submission/{sid}/pdf"
                                with sess.get(pdf_url, stream=True, timeout=60) as resp:
                                    if resp.status_code == 200:
                                        local_pdf = os.path.join(os.path.expanduser("~/.sloan_suite"),
                                                                 f"jtf_{uuid.uuid4().hex}_{sid}.pdf")
                                        _ensure_dir(local_pdf)
                                        with open(local_pdf, "wb") as out:
                                            shutil.copyfileobj(resp.raw, out)
                                        # Name the PDF. You can change to "{Customer} Measure Sheet {Date}.pdf" if preferred.
                                        pdf_idx = (index_counter + 1) if index_counter else 1
                                        pdf_name = f"{customer} {kind} {pdf_idx} {date_str}.pdf"
                                        if stage_spo:
                                            dl = self.cfg.get("organizer", {}).get("downloads_folder_path", "/Downloads")
                                            sp_pdf_path = f"{dl}/{pdf_name}"
                                            self.graph.upload_small(sp_pdf_path, local_pdf)
                                            try: os.remove(local_pdf)
                                            except Exception: pass
                                        else:
                                            dest = os.path.join(self.cfg.get("watch_folder", os.path.expanduser("~")), pdf_name)
                                            _ensure_dir(dest)
                                            shutil.move(local_pdf, dest)
                            except Exception as pdf_ex:
                                self.log(f"[JOTFORM] PDF fetch skipped {sid}: {pdf_ex}")

                            self.log(f"[JOTFORM] Processed submission {sid} for {customer} ({kind})")

                        # Next page
                        if len(items) < limit:
                            break
                        offset += limit

                    # After finishing this form round, persist the newest id we saw
                    if newest_id_this_round:
                        # Reload config, update cursor, save
                        cfg_live = load_config()
                        cfg_live.setdefault("jotform", {}).setdefault("cursors", {})
                        cfg_live["jotform"]["cursors"][form_id] = newest_id_this_round
                        save_config(cfg_live)
                        # Also keep our in-memory copy current
                        cursors[form_id] = newest_id_this_round

            except Exception as ex:
                self.log(f"[JOTFORM] Error {ex}\n{traceback.format_exc()}")

            # Sleep until next poll
            self.stop_evt.wait(poll_s)
