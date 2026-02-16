import json
import os
import tempfile
from typing import BinaryIO

from sqlalchemy.orm import Session

from server.models import Run, Entity, Match, Cluster
from server.dedup.runner import run_dedup
from server.services.survivor import pick_survivor_among_entity_dicts


def create_run(
    db: Session,
    entity_type: str,
    file: BinaryIO,
    params: str | None = None,
) -> Run:
    """
    Create a run: save uploaded CSV to temp file, run dedup from CSV (no JSON),
    persist entities/matches/clusters.
    """
    run = Run(
        entity_type=entity_type,
        source_type="csv",
        status="running",
        params_json=params,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            tmp_path = f.name
            f.write(file.read())

        try:
            params_dict = json.loads(params) if params else None
        except json.JSONDecodeError:
            params_dict = None
        result = run_dedup(entity_type, tmp_path, params_dict)

        entities_list = result.get("entities") or []
        matches_list = result.get("matches") or []
        clusters_list = result.get("clusters") or []

        # 1. Create entities and build external_id -> entity.id map
        ext_to_entity_id: dict[str, str] = {}
        raw_jsons_by_ext: dict[str, dict] = {}
        for e in entities_list:
            ext_id = e.get("external_id") or ""
            raw = e.get("raw_json") or {}
            raw_jsons_by_ext[ext_id] = raw
            entity = Entity(
                run_id=run.id,
                entity_type=entity_type,
                external_id=ext_id,
                raw_json=json.dumps(raw) if raw else None,
            )
            db.add(entity)
        db.flush()
        for ent in db.query(Entity).filter(Entity.run_id == run.id).all():
            ext_to_entity_id[ent.external_id] = ent.id

        # 2. Create matches
        for m in matches_list:
            a_ext = m.get("a_external_id")
            b_ext = m.get("b_external_id")
            a_id = ext_to_entity_id.get(a_ext)
            b_id = ext_to_entity_id.get(b_ext)
            if not a_id or not b_id:
                continue
            survivor_ext = m.get("recommended_survivor_external_id")
            survivor_id = ext_to_entity_id.get(survivor_ext) if survivor_ext else None
            if not survivor_id and a_id and b_id:
                survivor_ext = pick_survivor_among_entity_dicts(
                    [a_ext, b_ext],
                    raw_jsons_by_ext,
                    entity_type,
                )
                survivor_id = ext_to_entity_id.get(survivor_ext) if survivor_ext else None
            reasons = m.get("reasons_json") or []
            match = Match(
                run_id=run.id,
                entity_type=entity_type,
                a_entity_id=a_id,
                b_entity_id=b_id,
                score=float(m.get("score") or 0),
                reasons_json=json.dumps(reasons),
                recommended_survivor_entity_id=survivor_id,
                status="unreviewed",
            )
            db.add(match)
        db.flush()

        # 3. Create clusters
        for c in clusters_list:
            member_ext_ids = c.get("member_external_ids") or []
            member_entity_ids = [ext_to_entity_id.get(ext) for ext in member_ext_ids]
            member_entity_ids = [x for x in member_entity_ids if x]
            if not member_entity_ids:
                continue
            rec_ext = c.get("recommended_survivor_external_id")
            rec_entity_id = ext_to_entity_id.get(rec_ext) if rec_ext else None
            if not rec_entity_id and member_entity_ids:
                raw_by_id = {
                    eid: raw_jsons_by_ext.get(ext) or {}
                    for ext, eid in ext_to_entity_id.items()
                    if eid in member_entity_ids
                }
                rec_entity_id = pick_survivor_among_entity_dicts(
                    member_entity_ids,
                    raw_by_id,
                    entity_type,
                )
            cluster = Cluster(
                run_id=run.id,
                entity_type=entity_type,
                member_entity_ids_json=json.dumps(member_entity_ids),
                recommended_survivor_entity_id=rec_entity_id,
            )
            db.add(cluster)

        run.status = "completed"
        db.commit()
        db.refresh(run)
        return run

    except Exception as e:
        run.status = "failed"
        err_msg = str(e)
        run.params_json = json.dumps({"error": err_msg}) if err_msg else run.params_json
        db.commit()
        db.refresh(run)
        raise

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
