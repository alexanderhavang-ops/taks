"""Administrative exercise ORBAT using TAKS identities and neutral display grids.

This module makes rosters and map staging layouts, not combat deployments.
All geographic anchors are supplied by the caller as exercise data.
"""
import copy
import uuid
from .model import World, offset, point
from takctl.onboarding.identity_grammar import derive_grammar


def build_group_staging(anchor):
    """A small, inactive, fictional eight-person TAKS/FAL exercise roster."""
    position=point(anchor["position"])
    names=[("Erik","Lind"),("Sara","Holm"),("Johan","Berg"),("Lina","Ek"),("Oskar","Dahl"),("Maja","Lund"),("Nils","Strand"),("Anna","Vik")]
    members=[]
    for n,(first,last) in enumerate(names,1):
        identity=derive_grammar("hemvarnet",{"battalion_fal":"VQ","company":"R","platoon":"A","group":"E","n":n,"callsign_policy":"FALFAL"})
        members.append({"callsign":identity["callsign"],"position":offset(position,((n-1)//4)*2,((n-1)%4)*2),
            "role":"group_leader" if n==1 else "deputy" if n==2 else "member","readiness":"ready","group_id":"earq",
            "metadata":{"simulation":True,"fictional_person":True,"first_name":first,"last_name":last,"full_name":first+" "+last,
                "local_callsign":identity["callsign_variants"]["FAL"],"global_callsign":identity["callsign"],"team":"Green",
                "language":"en","tak_groups":["sim-earq"],"skill_level":"trained","leadership_style":"deliberate" if n==1 else "concise",
                "chat_rooms":["sim-earq"],"designation":"group leader" if n==1 else "deputy group leader" if n==2 else "soldier"}})
    w=World(capacity=8)
    w.apply("create",{"unit_id":"sim-group-earq","callsign":"EARQ","count":8,"position":position,"members":members,
        "request_id":"group-create","expected_revision":0,"metadata":{"exercise":"neutral staging","level":"group","anchor":anchor["label"]}})
    w.apply("marker_put",{"unit_id":"sim-group-earq","marker_id":"earq-hq","ttl_s":None,"callsign":"EARQ-HQ","position":position,
        "role":"HQ","metadata":{"level":"group","anchor":anchor["label"],"team":"Green"},"request_id":"group-hq","expected_revision":w.state["revision"]})
    w.apply("deactivate",{"unit_id":"sim-group-earq","request_id":"group-inactive","expected_revision":w.state["revision"]})
    w.state["orbat"]={"profile":"group-8-neutral-staging-v1","instance_id":str(uuid.uuid4()),"personnel":8,
        "mode":"inactive until explicitly started","naming_source":"TAKS identity grammar / FALFAL","anchor":anchor["label"]}
    apply_communications_roster(w.state)
    w.state["requests"]={}
    return w.state


def build_hv_staging(anchors, *, active=False):
    """Three user-selected companies, A–E platoons, E–H groups, 520 identities."""
    required = {"VQ", "RQ", "SQ", "TQ"}
    if not isinstance(anchors, dict) or set(anchors) != required:
        raise ValueError("Provide VQ/RQ/SQ/TQ exercise anchors")
    anchors = copy.deepcopy(anchors)
    for item in anchors.values():
        point(item["position"])
        if not isinstance(item.get("label"), str) or len(item["label"]) > 160: raise ValueError("Invalid anchor label")
    w = World(capacity=520)
    nodes, actors, local_aliases = [], [], {}
    person_serial = 0

    def node(uid, parent, label, level, owner, position, **metadata):
        metadata.setdefault("team",{"RQ":"Blue","SQ":"Green","TQ":"Orange"}.get(w.state["units"][owner]["metadata"].get("company"),"Cyan"))
        record = {"id":uid,"parent_id":parent,"label":label,"level":level,"owner_unit_id":owner,**metadata}
        nodes.append(record)
        role = "HQ" if level in ("battalion", "company", "platoon") else "exercise marker"
        w.apply("marker_put", {"unit_id":owner,"request_id":"node-"+str(len(nodes)),"expected_revision":w.state["revision"],
            "marker_id":uid,"ttl_s":None,"callsign":label,"position":position,"cot_type":"a-f-G-U-C-I",
            "role":role,"remarks":"EXERCISE STAGING ONLY | "+level+" | "+label,
            "metadata":{"hierarchy_id":uid,"parent_id":parent,"level":level,**metadata}})

    def unit(uid, label, members, position, parent, **metadata):
        for person in members: person.setdefault("group_id",parent)
        w.apply("create", {"unit_id":uid,"callsign":label,"count":len(members),"position":position,
            "request_id":"roster-"+str(len(w.state["units"])),"expected_revision":w.state["revision"],
            "members":members,"metadata":{"exercise":"neutral staging","language":"en","parent_hierarchy_id":parent,**metadata}})
        for e in w.state["units"][uid]["entities"]:
            md = e["metadata"]
            record = {"entity_id":e["id"],"uid":e["uid"],"unit_id":uid,"callsign":e["callsign"],
                      "local_callsign":md["local_callsign"],"parent_id":parent,**metadata}
            actors.append(record)
            local_aliases.setdefault(md["local_callsign"], []).append(e["uid"])

    def member(callsign, local, position, role="member", **metadata):
        nonlocal person_serial
        # Names are fictional and descriptive; the unique TAKS identity stays authoritative.
        firsts="Erik Sara Johan Lina Oskar Maja Nils Anna Emil Elin Axel Klara Hugo Ida Karl Sofia Viktor Emma Gustav Alma".split()
        lasts="Lind Holm Berg Ek Dahl Lund Strand Vik Boman Sund Nyberg Norberg Hedin Frisk Lindahl Sjoberg Ekman Holt Lindgren Nystrom Bergman Sundberg Falk Sand Holmberg Lundin".split()
        first,last=firsts[person_serial%len(firsts)],lasts[(person_serial//len(firsts))%len(lasts)]
        person_serial += 1
        metadata.setdefault("first_name",first);metadata.setdefault("last_name",last)
        metadata.setdefault("full_name",first+" "+last);metadata.setdefault("fictional_person",True)
        metadata.setdefault("designation",metadata.get("duty",role).replace('_',' '))
        metadata.setdefault("team",{"RQ":"Blue","SQ":"Green","TQ":"Orange"}.get(metadata.get("company"),"Cyan"))
        metadata.setdefault("tak_groups",["sim-"+metadata.get("company","vq").lower()])
        if metadata.get("group"):
            metadata["tak_groups"].append("sim-"+(metadata["group"]+metadata.get("company","")).lower())
        return {"callsign":callsign,"position":position,"role":role,"platform":"person",
                "readiness":"ready","metadata":{"simulation":True,"language":"en","local_callsign":local,
                    "global_callsign":callsign,"callsign_policy":"FALFAL",**metadata}}

    bhq = "hv-vq-command"; bp = anchors["VQ"]["position"]
    unit(bhq,"VQ-CMD",[member("VQ1","VQ1",offset(bp,0,-2),"HQ",duty="battalion_commander",callsign_policy="FAL"),
                        member("VQ2","VQ2",offset(bp,0,2),"deputy",duty="battalion_deputy",callsign_policy="FAL")],bp,"vq",battalion="VQ",level="command")
    node("vq",None,"VQ-BN-HQ","battalion",bhq,bp,anchor=anchors["VQ"]["label"])

    for letter in "RST":
        company = letter+"Q"; company_id = "vq-"+company.lower(); cp = anchors[company]["position"]
        hq = "hv-"+company.lower()+"-command"
        leaders=[]
        for n in (1,2):
            ctx={"battalion_fal":"VQ","company":letter,"n":n,"callsign_policy":"FALFAL"}
            name=derive_grammar("hemvarnet",ctx)
            leaders.append(member(name["callsign"],name["callsign_variants"]["FAL"],offset(cp,0,(n-1)*3),
                                  "HQ" if n==1 else "deputy",duty="company_commander" if n==1 else "company_deputy",
                                  leadership_style="calm and concise" if n==1 else "methodical",company=company))
        unit(hq,company+"-CMD",leaders,cp,company_id,battalion="VQ",company=company,level="command")
        node(company_id,"vq",company+"-CO-HQ","company",hq,cp,local_callsign=company,anchor=anchors[company]["label"])
        # Neutral roster display: A–D in a straight row; E beside the HQ.
        # Coordinates do not use terrain, cover, observation or weapons fields.
        for pindex,platoon in enumerate("ABCDE"):
            pp=offset(cp,60,(pindex-1.5)*60) if platoon!="E" else offset(cp,0,15)
            platoon_fal=platoon+letter; platoon_id=company_id+"-"+platoon.lower()
            for gindex,group in enumerate("EFGH"):
                gp=offset(pp,12,(gindex-1.5)*12)
                group_fal=group+platoon; group_id=platoon_id+"-"+group.lower()
                uid="hv-"+company.lower()+"-"+platoon.lower()+"-"+group.lower()
                members=[]
                for n in range(1,9):
                    naming=derive_grammar("hemvarnet",{"battalion_fal":"VQ","company":letter,"platoon":platoon,"group":group,"n":n,"callsign_policy":"FALFAL"})
                    members.append(member(naming["callsign"],naming["callsign_variants"]["FAL"],
                        offset(gp,(n-1)//4*2,((n-1)%4-1.5)*2),"group_leader" if n==1 else "deputy" if n==2 else "member",
                        company=company,platoon=platoon_fal,group=group_fal,member_number=n))
                unit(uid,group_fal+company,members,gp,group_id,battalion="VQ",company=company,platoon=platoon_fal,group=group_fal,level="group")
                if gindex==0:
                    node(platoon_id,company_id,platoon_fal+company+"-PLT","platoon",uid,pp,local_callsign=platoon_fal,strength=32)
                node(group_id,platoon_id,group_fal+company+"-GRP","group",uid,gp,local_callsign=group_fal,strength=8)

    comms="hv-vq-ledning"; lp=offset(bp,-15,0)
    unit(comms,"VQ-LEDNING",[member(f"VQ-LP{n:02d}",f"LP{n:02d}",offset(lp,((n-1)//5)*2,((n-1)%5)*2),
        "HQ" if n==1 else "member",duty="communications_and_administration",callsign_policy="exercise_function_alias") for n in range(1,21)],
        lp,"vq-ledning",battalion="VQ",level="platoon",function="communications_and_administration")
    node("vq-ledning","vq","VQ-LEDNING-PLT","platoon",comms,lp,strength=20,naming="exercise function alias")

    for i,(function,count) in enumerate((("S1",2),("S2",2),("S3/5",3),("S4",2),("S6",3))):
        token=function.replace("/",""); uid="hv-vq-"+token.lower(); hp=offset(bp,-30,i*8)
        unit(uid,"VQ-"+token,[member(f"VQ-{token}-{n:02d}",f"{function}-{n:02d}",offset(hp,(n-1)*2,0),
            "staff_lead" if n==1 else "member",function=function,callsign_policy="exercise_function_alias") for n in range(1,count+1)],
            hp,"vq-"+token.lower(),battalion="VQ",level="staff",function=function)
        node("vq-"+token.lower(),"vq","VQ-"+token+"-STAFF","staff",uid,hp,function=function,strength=count)

    people=w.entities()
    if len(people)!=520 or len({e["callsign"] for e in people})!=520 or len({e["uid"] for e in people})!=520:
        raise ValueError("Roster count or unique identity check failed")
    w.state["orbat"]={"profile":"hv-520-neutral-staging-v1","instance_id":uuid.uuid4().hex,"battalion":"VQ","personnel":520,
        "companies":["RQ","SQ","TQ"],"company_strength":162,"line_personnel":384,"company_hq_platoon_personnel":96,
        "company_commanders":6,"battalion_commanders":2,"communications_admin":20,"staff":12,
        "staff_strengths":{"S1":2,"S2":2,"S3/5":3,"S4":2,"S6":3},
        "naming_source":"TAKS identity_grammar.py / fal.py; uploaded FAL-A 2020 sections 1.1 and 1.2.3",
        "group_letters":["E","F","G","H"],"nodes":nodes,"actors":actors,"local_aliases":local_aliases,
        "layout":"neutral exercise staging grids; no combat-position selection","language":"en",
        "headcount_note":"32 people per A–E platoon; platoon command markers do not add personnel. Communications and staff aliases are exercise-defined"}
    if not active:
        for u in w.state["units"].values():u["active"]=False
    apply_communications_roster(w.state)
    w.state["requests"]={}
    return w.state


def command_nodes(state):
    """Resolve command appointments against the administrative exercise roster."""
    units = state["units"]
    actors = {actor["id"]: actor for unit in units.values() for actor in unit["entities"]}
    hierarchy = {row["id"]: row for row in state["orbat"].get("nodes", []) if row["owner_unit_id"] in units}
    primary_nodes = {row["unit_id"]: row["parent_id"] for row in state["orbat"].get("actors", [])
                     if row["parent_id"] in hierarchy and row["unit_id"] in units}
    for unit_id, unit in units.items():
        if unit_id not in primary_nodes:
            node_id = unit_id if unit_id not in hierarchy else "unit:" + unit_id
            primary_nodes[unit_id] = node_id
            hierarchy[node_id] = {"id": node_id, "parent_id": None, "owner_unit_id": unit_id,
                                  "label": unit["callsign"], "level": "squad"}

    def contact(entity_id):
        if entity_id is None:
            return None
        actor = actors[entity_id]
        return {"entity_id": actor["id"], "uid": actor["uid"], "callsign": actor["callsign"]}

    resolved = {}
    for node_id, node in hierarchy.items():
        unit = units[node["owner_unit_id"]]
        members = unit["entities"]
        overrides = state.get("command_assignments", {}).get(node_id, {})
        commander = overrides.get("commander_entity_id", members[0]["id"])
        deputy = overrides.get("deputy_entity_id", next((e["id"] for e in members if e["role"] == "deputy"), None))
        if commander == deputy:
            deputy = None
        resolved[node_id] = {
            "id": node_id, "label": node["label"], "unit_id": unit["id"],
            "level": overrides.get("level", node["level"]),
            "parent_id": overrides.get("parent_id", node["parent_id"]),
            "commander": contact(commander), "deputy": contact(deputy),
            "acting_commander": (node["level"] == "platoon" and primary_nodes[unit["id"]] != node_id
                                 and "commander_entity_id" not in overrides),
        }
    return resolved, primary_nodes


def chain(nodes, node_id):
    seen = set()
    while node_id in nodes and node_id not in seen:
        seen.add(node_id)
        node = nodes[node_id]
        yield node
        node_id = node["parent_id"]


def actor_command_context(state, entity):
    unit_id = next(unit["id"] for unit in state["units"].values() if entity in unit["entities"])
    nodes, primary = command_nodes(state)
    reporting_chain = list(chain(nodes, primary[unit_id]))
    superior = next((row["commander"] for row in reporting_chain if row["commander"]
                     and row["commander"]["entity_id"] != entity["id"]), None)
    led = [node["id"] for node in nodes.values()
           if node["commander"] and node["commander"]["entity_id"] == entity["id"]]
    return {"chain": reporting_chain, "reports_to": superior,
            "direct_subordinate_echelons": [row for row in nodes.values()
                                            if row["parent_id"] in led and row["id"] not in led]}


def configure_command(state, unit, args):
    nodes, primary = command_nodes(state)
    node_id = args.get("hierarchy_id", primary[unit["id"]])
    if not isinstance(node_id, str) or node_id not in nodes or nodes[node_id]["unit_id"] != unit["id"]:
        raise ValueError("Command echelon is not owned by this unit")
    fields = {"commander_entity_id", "deputy_entity_id", "parent_id", "level"} & args.keys()
    if not fields:
        raise ValueError("Supply a command appointment, parent, or level")
    if fields & {"parent_id", "level"} and any(row["id"] == node_id for row in state["orbat"].get("nodes", [])):
        raise ValueError("Imported ORBAT defines this echelon's parent and level")

    if "level" in fields and args["level"] not in ("squad", "platoon", "company", "battalion"):
        raise ValueError("Invalid command echelon level")
    if "parent_id" in fields:
        parent = args["parent_id"]
        if parent is not None and (not isinstance(parent, str) or parent not in nodes or
                                   any(row["id"] == node_id for row in chain(nodes, parent))):
            raise ValueError("Command parent must refer to an existing echelon outside this branch")

    actor_ids = {e["id"] for member_unit in state["units"].values() for e in member_unit["entities"]}
    for field in fields & {"commander_entity_id", "deputy_entity_id"}:
        candidate = args[field]
        if candidate is not None and (not isinstance(candidate, str) or candidate not in actor_ids):
            raise ValueError(f"{field} must identify an exercise actor or be null")
    assignment = {**state["command_assignments"].get(node_id, {}), **{field: args[field] for field in fields}}
    commander = assignment.get("commander_entity_id", (nodes[node_id]["commander"] or {}).get("entity_id"))
    deputy = assignment.get("deputy_entity_id")
    if commander is not None and commander == deputy:
        raise ValueError("Commander and deputy must be distinct")
    state["command_assignments"][node_id] = assignment
    return command_nodes(state)[0][node_id]


def apply_communications_roster(state):
    """Use the same exercise-only addresses in TAK, GeoChat, XMPP and Mumble."""
    nodes, primary = command_nodes(state)
    for uid, unit in state["units"].items():
        rooms = ["sim-" + row["id"].removeprefix("sim-") for row in chain(nodes, primary[uid])]
        for actor in unit["entities"]:
            actor["metadata"].update(tak_groups=rooms, chat_rooms=rooms, voice_channels=rooms)
            actor.setdefault("sustainment", {"health_pct": 100, "satiation_pct": 75, "hydration_pct": 75,
                                              "rations": 3, "water_ml": 2000, "duty_status": "ready",
                                              "accounted_through_clock_s": 0})
