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
        members.append({"callsign":"SIM-"+identity["callsign"],"position":offset(position,((n-1)//4)*2,((n-1)%4)*2),
            "role":"group_leader" if n==1 else "deputy" if n==2 else "member","readiness":"ready","group_id":"earq",
            "metadata":{"simulation":True,"fictional_person":True,"first_name":first,"last_name":last,"full_name":first+" "+last,
                "local_callsign":identity["callsign_variants"]["FAL"],"global_callsign":identity["callsign"],"team":"Green",
                "language":"en","tak_groups":["sim-earq"],"skill_level":"trained","leadership_style":"deliberate" if n==1 else "concise",
                "chat_rooms":["sim-earq"],"designation":"group leader" if n==1 else "deputy group leader" if n==2 else "soldier"}})
    w=World(capacity=8)
    w.apply("create",{"unit_id":"sim-group-earq","callsign":"SIM-EARQ","count":8,"position":position,"members":members,
        "request_id":"group-create","expected_revision":0,"metadata":{"exercise":"neutral staging","level":"group","anchor":anchor["label"]}})
    w.apply("marker_put",{"unit_id":"sim-group-earq","marker_id":"earq-hq","callsign":"SIM-EARQ-HQ","position":position,
        "role":"HQ","metadata":{"level":"group","anchor":anchor["label"]},"request_id":"group-hq","expected_revision":w.state["revision"]})
    w.apply("deactivate",{"unit_id":"sim-group-earq","request_id":"group-inactive","expected_revision":w.state["revision"]})
    w.state["orbat"]={"profile":"group-8-neutral-staging-v1","instance_id":str(uuid.uuid4()),"personnel":8,
        "mode":"inactive until explicitly started","naming_source":"TAKS identity grammar / FALFAL","anchor":anchor["label"]}
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

    def node(uid, parent, label, level, owner, position, **metadata):
        record = {"id":uid,"parent_id":parent,"label":label,"level":level,"owner_unit_id":owner,**metadata}
        nodes.append(record)
        role = "HQ" if level in ("battalion", "company", "platoon") else "exercise marker"
        w.apply("marker_put", {"unit_id":owner,"request_id":"node-"+str(len(nodes)),"expected_revision":w.state["revision"],
            "marker_id":uid,"callsign":"SIM-"+label,"position":position,"cot_type":"a-f-G-U-C-I",
            "role":role,"remarks":"EXERCISE STAGING ONLY | "+level+" | "+label,
            "metadata":{"hierarchy_id":uid,"parent_id":parent,"level":level,**metadata}})

    def unit(uid, label, members, position, parent, **metadata):
        for person in members: person.setdefault("group_id",parent)
        w.apply("create", {"unit_id":uid,"callsign":"SIM-"+label,"count":len(members),"position":position,
            "request_id":"roster-"+str(len(w.state["units"])),"expected_revision":w.state["revision"],
            "members":members,"metadata":{"exercise":"neutral staging","language":"en","parent_hierarchy_id":parent,**metadata}})
        for e in w.state["units"][uid]["entities"]:
            md = e["metadata"]
            record = {"entity_id":e["id"],"uid":e["uid"],"unit_id":uid,"callsign":e["callsign"],
                      "local_callsign":md["local_callsign"],"parent_id":parent,**metadata}
            actors.append(record)
            local_aliases.setdefault(md["local_callsign"], []).append(e["uid"])

    def member(callsign, local, position, role="member", **metadata):
        return {"callsign":"SIM-"+callsign,"position":position,"role":role,"platform":"person",
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
    w.state["requests"]={}
    return w.state
