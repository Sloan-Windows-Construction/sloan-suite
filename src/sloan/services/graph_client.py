import os, time, random
from typing import Dict, Optional
import requests, msal



GRAPH = "https://graph.microsoft.com/v1.0"

def _default_timeout(kwargs, connect=12, read=45):
    # allow caller to override, else supply sane defaults
    if "timeout" not in kwargs or kwargs["timeout"] is None:
        kwargs["timeout"] = (connect, read)
    return kwargs

class GraphClient:
    def __init__(self, cfg: Dict):
        self.cfg = cfg
        self._token: Optional[str] = None
        self._sess = requests.Session()
        self._folder_cache = set()  # cache drive-relative folder paths we’ve ensured

        # Robust retries for transient & throttling errors
        from requests.adapters import HTTPAdapter
        from urllib3.util import Retry

        retry = Retry(
            total=6,
            connect=6,
            read=6,
            backoff_factor=1.5,           # 1.5s, 3s, 4.5s, 6.75s...
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET","PUT","POST","PATCH"])
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._sess.mount("https://", adapter)
        self._sess.mount("http://", adapter)

    # -------------------- auth --------------------
    def _get_token(self, force=False) -> str:
        if self._token and not force:
            return self._token
        g = self.cfg.get("graph", {})
        tenant = g.get("tenant_id"); cid = g.get("client_id"); secret = g.get("client_secret")
        if not all([tenant, cid, secret]):
            raise RuntimeError("Graph credentials not configured")
        app = msal.ConfidentialClientApplication(
            client_id=cid, client_credential=secret, authority=f"https://login.microsoftonline.com/{tenant}"
        )
        scope = ["https://graph.microsoft.com/.default"]
        result = app.acquire_token_silent(scopes=scope, account=None) or app.acquire_token_for_client(scopes=scope)
        if "access_token" not in result:
            raise RuntimeError(f"MSAL token error: {result}")
        self._token = result["access_token"]
        self._sess.headers.update({"Authorization": f"Bearer {self._token}"})
        return self._token

    def _authed(self):
        if not self._token:
            self._get_token()
        return self._sess

    def _retry_on_401(self, req_fn, *args, **kwargs):
        _default_timeout(kwargs)  # ensure timeouts on every call
        r = req_fn(*args, **kwargs)
        if r.status_code in (401, 403):
            # refresh once
            self._get_token(force=True)
            # small jitter before retry
            time.sleep(0.3 + random.random() * 0.7)
            r = req_fn(*args, **kwargs)
        return r

    # -------------------- utils --------------------
    def _drive_base(self) -> str:
        drive_id = self.cfg.get("graph", {}).get("drive_id")
        if not drive_id:
            raise RuntimeError("graph.drive_id missing in config")
        return f"{GRAPH}/drives/{drive_id}"

    @staticmethod
    def _norm_rel(path: str) -> str:
        path = (path or "").replace("\\", "/")
        path = "/".join(p for p in path.split("/") if p != "")
        return path.lstrip("/")

    # -------------------- folders --------------------
    def ensure_folder(self, folder_path: str):
        """
        Ensure a (possibly nested) folder exists under the drive root.
        Caches successes to avoid repeated GETs.
        """
        rel = self._norm_rel(folder_path).strip("/")
        if not rel:
            return
        if rel in self._folder_cache:
            return

        parts = rel.split("/")
        built = ""
        for seg in parts:
            built = f"{built}/{seg}" if built else seg
            if built in self._folder_cache:
                continue

            # GET the node; if 404, create it
            url_get = f"{self._drive_base()}/root:/{built}"
            r = self._retry_on_401(self._authed().get, url_get)
            if r.status_code == 200:
                self._folder_cache.add(built)
                continue
            if r.status_code == 404:
                parent = os.path.dirname(built)
                if parent and parent != ".":
                    parent_url = f"{self._drive_base()}/root:/{parent}:/children"
                else:
                    parent_url = f"{self._drive_base()}/root:/children"
                body = {"name": seg, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}
                rc = self._retry_on_401(self._authed().post, parent_url, json=body)
                if rc.status_code not in (200, 201):
                    raise RuntimeError(f"ensure_folder create failed {rc.status_code} {rc.text} for {built}")
                self._folder_cache.add(built)
            else:
                # network/timeouts show up here via requests exceptions, but if Graph returns 5xx, bubble up
                raise RuntimeError(
                    f"ensure_folder get failed {r.status_code} {r.text} for {built}"
                )

    # -------------------- files --------------------
    def upload_small(self, target_path: str, local_file: str):
        """
        Upload a small file (<= 4 MiB) to the drive at target_path.
        """
        rel = self._norm_rel(target_path)  # e.g. 'Downloads/myfile.jpg'
        parent = os.path.dirname(rel)
        if parent and parent != ".":
            self.ensure_folder(parent)

        url = f"{self._drive_base()}/root:/{rel}:/content"
        with open(local_file, "rb") as fh:
            r = self._retry_on_401(self._authed().put, url, data=fh)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"upload_small failed: {r.status_code} {r.text}\nTarget: {rel}")
        return r.json()

    def move_item(self, item_id: str, new_parent_id: str, new_name: Optional[str] = None):
        url = f"{self._drive_base()}/items/{item_id}"
        data = {"parentReference": {"id": new_parent_id}}
        if new_name:
            data["name"] = new_name
        r = self._retry_on_401(self._authed().patch, url, json=data)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"move_item failed: {r.status_code} {r.text}")
        return r.json()

    def get_by_path(self, path: str):
        rel = self._norm_rel(path)
        url = f"{self._drive_base()}/root:/{rel}"
        r = self._retry_on_401(self._authed().get, url)
        return r.json() if r.status_code == 200 else None
