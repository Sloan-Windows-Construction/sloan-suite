import os
from typing import Dict

class Organizer:
    def __init__(self, cfg: Dict, graph_client):
        self.cfg = cfg
        self.graph = graph_client

    def ensure_customer_tree(self, customer: str):
        org = self.cfg.get("organizer", {})
        customer_root = org.get("customer_root_path", "/Customers")
        cust_path = f"{customer_root}/{customer}"
        # ensure top levels
        self.graph.ensure_folder(os.path.dirname(customer_root), os.path.basename(customer_root).lstrip("/"))
        self.graph.ensure_folder(customer_root, customer)
        made = {}
        for sub in org.get("create_default_tree", []):
            parent = cust_path + os.path.dirname(sub)
            self.graph.ensure_folder(parent, os.path.basename(sub))
            node = self.graph.get_by_path(cust_path + sub)
            if node: made[sub] = node["id"]
        return made

    def route_keyword(self, keyword_acr: str) -> str:
        return self.cfg.get("organizer", {}).get("routing", {}).get(keyword_acr, "/Extra")

    def move_uploaded_to_customer(self, uploaded_item: Dict, customer: str, keyword_acr: str):
        self.ensure_customer_tree(customer)
        dest_rel = self.route_keyword(keyword_acr)
        dest_path = f"{self.cfg['organizer']['customer_root_path']}/{customer}{dest_rel}"
        dest_node = self.graph.get_by_path(dest_path)
        if not dest_node:
            raise RuntimeError(f"Destination path missing: {dest_path}")
        return self.graph.move_item(uploaded_item["id"], dest_node["id"], new_name=uploaded_item.get("name"))