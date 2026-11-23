"""Builds aio-software-generated.ttl: software modules (with their time and space resolution)
and the extra reference workflows, single-software and coupled. DRAFT FOR EXPERT VALIDATION.

Since AIO 0.9.0 these belong to the extension "software implementations" (aiosw:,
https://w3id.org/aio/software#); the roles, templates and coupling types they use come from
the extension "model composition" (aiowf:); methods, software and processes from the core (aio:).
The ontology header and the hand-maintained part of the extension are in aio-software.ttl.

Why a generator: each workflow needs its steps, and each module the same six facts. A
table is easier to review than hand-written Turtle. Edit the tables, run

    python ontology/build_software_ttl.py

then load the file into GraphDB (docker-compose does it on a fresh volume).

Sources consulted (Nov 2026), for the module options and usual practice:
  MIKE SHE user guide (UZ: Richards / gravity flow / two-layer; per-component time steps)
      https://userdoc.mikeshe.mikepoweredbydhi.com/2026/UI/SetupDataTab/Simulation/
  HEC-HMS methods (loss, transform, baseflow, routing; SMA for continuous simulation)
      https://knowledge.civilgeo.com/hec-hms-hydrology-methods
  HEC-RAS 2D rain-on-grid infiltration (deficit-constant, CN, Green-Ampt)
      https://www.frontiersin.org/journals/water/articles/10.3389/frwa.2024.1384205/full
  SWMM 1D-2D dual drainage with Iber or TELEMAC-2D
      https://core.ac.uk/download/344693212.pdf
  MIKE FLOOD (MIKE 11 + MIKE 21 coupling)
      https://en.wikipedia.org/wiki/MIKE_FLOOD
  TELEMAC-2D + GAIA morphodynamics
      https://eprints.hrwallingford.com/id/eprint/1554/
Resolutions are the ranges usually reported in practice, not limits of the software.
"""
import pathlib

HERE = pathlib.Path(__file__).parent

# ---------------------------------------------------------------------------------------
# Software modules: (software, method) -> module name, time step, time-step classes,
# spatial unit, usual spatial resolution, note
# ---------------------------------------------------------------------------------------
MODULES = {
    # HEC-HMS: lumped or gridded subbasins, one computation interval for the whole run
    ("HEC-HMS", "SCS-CN"): ("Loss: SCS curve number", "computation interval 5 min – 1 h (event)", ["SubHourly", "Hourly"], "subbasin (lumped) or grid cell (gridded)", "subbasins 1–100 km²; grid 0.5–2 km"),
    ("HEC-HMS", "Green-Ampt"): ("Loss: Green and Ampt", "5 min – 1 h", ["SubHourly", "Hourly"], "subbasin or grid cell", "subbasins 1–100 km²"),
    ("HEC-HMS", "SoilMoistureAccounting"): ("Loss: soil moisture accounting (5 layers)", "1 h – 1 day (continuous)", ["Hourly", "Daily"], "subbasin", "subbasins 10–1 000 km²"),
    ("HEC-HMS", "Clark-UH"): ("Transform: Clark unit hydrograph", "5 min – 1 h", ["SubHourly", "Hourly"], "subbasin", "subbasins 1–100 km²"),
    ("HEC-HMS", "ModClark"): ("Transform: ModClark (gridded)", "5 min – 1 h", ["SubHourly", "Hourly"], "grid cell", "SHG grid 0.5–2 km"),
    ("HEC-HMS", "KinematicWave"): ("Transform: kinematic wave (overland planes)", "1 – 15 min", ["SubHourly"], "overland planes + collector channels", "small subbasins < 10 km²"),
    ("HEC-HMS", "LinearReservoir"): ("Baseflow: linear reservoir", "same as the run", ["SubHourly", "Hourly", "Daily"], "subbasin", "subbasins 1–1 000 km²"),
    ("HEC-HMS", "Muskingum-Cunge"): ("Routing: Muskingum-Cunge", "run interval, automatic sub-steps", ["SubHourly", "Hourly"], "reach", "reaches 1–50 km"),
    ("HEC-HMS", "DiffusiveWave2D"): ("Transform: 2D diffusion wave (HEC-HMS 4.11+)", "1 – 5 min", ["SubHourly"], "2D mesh cell", "cells 30–200 m"),
    ("HEC-HMS", "Penman-Monteih"): ("Evapotranspiration: Penman-Monteith", "1 h – 1 day", ["Hourly", "Daily"], "subbasin", "subbasins 10–1 000 km²"),
    # HEC-RAS: 1D cross-sections, 2D unstructured mesh, adaptive time step
    ("HEC-RAS", "Saint-VenantEquations1D"): ("1D unsteady flow (Saint-Venant)", "1 s – 5 min", ["SubHourly"], "cross-section", "cross-sections every 50–500 m"),
    ("HEC-RAS", "ShallowWaterEquations2D"): ("2D unsteady flow (full momentum / SWE)", "1 – 30 s (Courant-based), output 5–15 min", ["SubHourly"], "mesh cell", "cells 5–50 m, refined 1–10 m"),
    ("HEC-RAS", "DiffusiveWave2D"): ("2D unsteady flow (diffusion wave)", "5 – 60 s", ["SubHourly"], "mesh cell", "cells 10–100 m"),
    ("HEC-RAS", "SCS-CN"): ("2D infiltration: curve number (rain-on-grid)", "same as the 2D run", ["SubHourly"], "mesh cell", "cells 5–50 m"),
    ("HEC-RAS", "EngelundHansen"): ("Sediment: Engelund-Hansen transport function", "computation increment 1 min – 1 h", ["SubHourly", "Hourly"], "cross-section", "cross-sections every 50–500 m"),
    ("HEC-RAS", "ExnerEquation"): ("Sediment: Exner bed update", "computation increment 1 min – 1 h", ["SubHourly", "Hourly"], "cross-section", "cross-sections every 50–500 m"),
    # MIKE SHE: grid, each component on its own time step
    ("MIKESHE", "Penman-Monteih"): ("Climate: reference ET input (Penman-Monteith)", "hourly to daily input", ["Hourly", "Daily"], "grid cell", "grid 50–1 000 m (typ. 100–500 m)"),
    ("MIKESHE", "RutterModel"): ("ET: canopy interception (Rutter)", "with the UZ step (≤ 2 h)", ["Hourly", "SubHourly"], "grid cell", "grid 100–500 m"),
    ("MIKESHE", "TemperatureIndexMethod"): ("Snow melt: degree-day", "with the UZ step", ["Hourly", "Daily"], "grid cell", "grid 100–500 m"),
    ("MIKESHE", "RichardsEquation"): ("Unsaturated zone: Richards equation", "UZ step ≤ 2 h", ["SubHourly", "Hourly"], "grid column, vertical nodes 1–10 cm", "grid 100–500 m"),
    ("MIKESHE", "Green-Ampt"): ("Unsaturated zone: Green-Ampt infiltration", "UZ step ≤ 2 h", ["SubHourly", "Hourly"], "grid column", "grid 50–500 m"),
    ("MIKESHE", "KristenJensen"): ("ET: Kristensen-Jensen actual ET", "with the UZ step", ["Hourly", "SubHourly"], "grid cell", "grid 100–500 m"),
    ("MIKESHE", "DiffusiveWave2D"): ("Overland flow: 2D diffusive wave", "OL step seconds – minutes", ["SubHourly"], "grid cell", "grid 50–500 m"),
    ("MIKESHE", "FiniteDifferenceGroundwaterFlow"): ("Saturated zone: 3D finite difference", "SZ step 6 – 24 h", ["Hourly", "Daily"], "grid cell × computational layers", "grid 100–1 000 m"),
    ("MIKESHE", "LinearReservoir"): ("Saturated zone: linear reservoir", "SZ step 6 – 24 h", ["Hourly", "Daily"], "sub-catchment zones", "zones 1–100 km²"),
    ("MIKE11", "Saint-VenantEquations1D"): ("MIKE 11 HD: 1D river (Saint-Venant)", "10 s – 5 min", ["SubHourly"], "h-points along branches", "h-points every 100–1 000 m"),
    ("MIKE21", "ShallowWaterEquations2D"): ("MIKE 21 HD: 2D floodplain (FM mesh)", "seconds (CFL-based)", ["SubHourly"], "mesh element", "elements 5–100 m"),
    # SWAT: HRUs inside subbasins, daily (sub-daily with Green-Ampt)
    ("SWAT", "Penman-Monteih"): ("PET: Penman-Monteith", "daily", ["Daily"], "HRU", "HRUs within subbasins of 1–1 000 km²"),
    ("SWAT", "TemperatureIndexMethod"): ("Snow: degree-day snowmelt", "daily", ["Daily"], "HRU / elevation band", "HRUs"),
    ("SWAT", "LayeredSoilWaterBudget"): ("Soil water: layered storage routing", "daily", ["Daily"], "HRU, up to 10 soil layers", "HRUs"),
    ("SWAT", "RootzoneStress"): ("Plant ET: root-zone water stress", "daily", ["Daily"], "HRU", "HRUs"),
    ("SWAT", "SCS-CN"): ("Surface runoff: SCS curve number", "daily", ["Daily"], "HRU", "HRUs"),
    ("SWAT", "Green-Ampt"): ("Surface runoff: Green-Ampt (sub-daily)", "1 min – 1 h (typ. hourly)", ["SubHourly", "Hourly"], "HRU", "HRUs"),
    ("SWAT", "SCS-UH"): ("Sub-daily unit hydrograph", "1 h", ["Hourly"], "subbasin", "subbasins 1–1 000 km²"),
    ("SWAT", "ConceptualRoutingReservoir"): ("Surface runoff lag (storage)", "daily", ["Daily"], "subbasin", "subbasins"),
    ("SWAT", "LinearReservoir"): ("Groundwater: shallow aquifer return flow", "daily", ["Daily"], "HRU", "HRUs"),
    ("SWAT", "Muskingum-Cunge"): ("Channel routing: Muskingum", "daily (or sub-daily)", ["Daily", "Hourly"], "reach", "one reach per subbasin"),
    ("SWAT", "PollutantBuildupWashoff"): ("Nutrient and pesticide loading", "daily", ["Daily"], "HRU", "HRUs"),
    ("MODFLOW", "FiniteDifferenceGroundwaterFlow"): ("Groundwater flow (block-centred finite difference)", "stress periods days – months, sub-steps", ["Daily", "MonthlyOrLonger"], "grid cell × layer", "cells 50–1 000 m"),
    # TELEMAC / Iber / SWMM
    ("TELEMAC-2D", "ShallowWaterEquations2D"): ("TELEMAC-2D hydrodynamics", "0.5 – 10 s", ["SubHourly"], "triangular mesh element", "elements 2–100 m"),
    ("TELEMAC", "FiniteVolumeSedimentTransport"): ("GAIA: sediment transport and bed evolution", "coupled to TELEMAC-2D, every n hydro steps", ["SubHourly"], "triangular mesh element", "elements 2–100 m"),
    ("IberPlus", "ShallowWaterEquations2D"): ("Iber+ 2D hydrodynamics (GPU)", "0.1 – 5 s", ["SubHourly"], "mesh element", "elements 1–50 m"),
    ("IberPlus", "MeyerPeterMuller"): ("Bedload: Meyer-Peter Müller", "with the 2D step", ["SubHourly"], "mesh element", "elements 1–50 m"),
    ("IberPlus", "ExnerEquation"): ("Bed evolution: Exner", "with the 2D step", ["SubHourly"], "mesh element", "elements 1–50 m"),
    ("SWMM", "HortonInfiltrationModel"): ("Infiltration: Horton", "runoff wet step 1 – 5 min", ["SubHourly"], "subcatchment", "subcatchments 0.1–100 ha"),
    ("SWMM", "NonLinearReservoir"): ("Surface runoff: non-linear reservoir", "runoff wet step 1 – 5 min", ["SubHourly"], "subcatchment", "subcatchments 0.1–100 ha"),
    ("SWMM", "Saint-VenantEquations1D"): ("Flow routing: dynamic wave", "routing step 1 – 30 s", ["SubHourly"], "conduit / node", "pipes and channels"),
    ("SWMM", "PollutantBuildupWashoff"): ("Water quality: build-up / wash-off", "runoff step", ["SubHourly"], "subcatchment", "subcatchments 0.1–100 ha"),
    # France / research codes
    ("ISBA", "Penman-Monteih"): ("ISBA surface energy balance", "5 min internal, daily output", ["SubHourly", "Daily"], "grid cell", "8 km grid (SAFRAN)"),
    ("ISBA", "LayeredSoilWaterBudget"): ("ISBA soil layers", "5 min internal, daily output", ["SubHourly", "Daily"], "grid cell", "8 km grid"),
    ("ISBA", "RootzoneStress"): ("ISBA transpiration with root-zone stress", "5 min internal", ["SubHourly"], "grid cell", "8 km grid"),
    ("SIM2", "FiniteDifferenceGroundwaterFlow"): ("MODCOU aquifers and river routing", "daily", ["Daily"], "nested grid cell", "1–4 km nested grid"),
    ("Python-R", "HargeavesMethod"): ("PET input (e.g. airGR PE_Oudin / Hargreaves)", "daily", ["Daily"], "catchment", "whole catchment"),
    ("Python-R", "GR4Jmodel"): ("GR4J (airGR)", "daily", ["Daily"], "catchment (lumped)", "catchments 10–10 000 km²"),
}

# ---------------------------------------------------------------------------------------
# Extra reference workflows: id, label, template, coupling, note, steps
#   step = (method, [roles], software)
# ---------------------------------------------------------------------------------------
CHAINS = [
    ("RC_HMS_SMA_Continuous", "HEC-HMS continuous (soil moisture accounting)", "Tpl_ContinuousWaterBalance",
     "InternalCoupling", "Continuous simulation in HEC-HMS: SMA loss with its groundwater layers, Clark transform, linear-reservoir baseflow, Muskingum-Cunge routing.",
     [("Penman-Monteih", ["Role_PET"], "HEC-HMS"), ("SoilMoistureAccounting", ["Role_SoilWaterBudget", "Role_ExcessRainfall"], "HEC-HMS"),
      ("Clark-UH", ["Role_RunoffTransform"], "HEC-HMS"), ("LinearReservoir", ["Role_Baseflow"], "HEC-HMS"),
      ("Muskingum-Cunge", ["Role_ChannelRouting"], "HEC-HMS")]),
    ("RC_HMS_KinematicWave", "HEC-HMS event flood (kinematic wave)", "Tpl_EventFloodHydrograph",
     "InternalCoupling", "Small or urbanised subbasins: Green-Ampt loss, kinematic-wave overland planes, Muskingum-Cunge routing.",
     [("Green-Ampt", ["Role_ExcessRainfall"], "HEC-HMS"), ("KinematicWave", ["Role_RunoffTransform"], "HEC-HMS"),
      ("Muskingum-Cunge", ["Role_ChannelRouting"], "HEC-HMS")]),
    ("RC_HMS_RAS1D_Inundation", "HEC-HMS → HEC-RAS 1D river levels", "Tpl_FloodInundation",
     "OfflineOneWay", "Hydrographs from HEC-HMS as upstream and lateral boundary conditions of a 1D unsteady HEC-RAS river model: water levels along the river.",
     [("SCS-CN", ["Role_ExcessRainfall"], "HEC-HMS"), ("Clark-UH", ["Role_RunoffTransform"], "HEC-HMS"),
      ("LinearReservoir", ["Role_Baseflow"], "HEC-HMS"), ("Saint-VenantEquations1D", ["Role_Hydraulics"], "HEC-RAS")]),
    ("RC_RAS2D_RainOnGrid", "HEC-RAS 2D rain-on-grid", "Tpl_FloodInundation",
     "InternalCoupling", "Rainfall applied directly on the 2D mesh with curve-number infiltration; the same 2D solver routes runoff and floods. Infiltrated water leaves the model (no return flow).",
     [("SCS-CN", ["Role_ExcessRainfall"], "HEC-RAS"), ("ShallowWaterEquations2D", ["Role_RunoffTransform", "Role_Hydraulics"], "HEC-RAS")]),
    ("RC_MIKESHE_MIKEFLOOD", "MIKE SHE + MIKE 11 + MIKE 21 (MIKE FLOOD)", "Tpl_FloodInundation",
     "TwoWayCoupling", "Catchment runoff in MIKE SHE, river in MIKE 11, floodplain in MIKE 21, dynamically coupled through MIKE FLOOD links.",
     [("Green-Ampt", ["Role_ExcessRainfall"], "MIKESHE"), ("DiffusiveWave2D", ["Role_RunoffTransform"], "MIKESHE"),
      ("Saint-VenantEquations1D", ["Role_ChannelRouting"], "MIKE11"), ("ShallowWaterEquations2D", ["Role_Hydraulics"], "MIKE21")]),
    ("RC_MIKESHE_LinearReservoirSZ", "MIKE SHE with linear-reservoir groundwater", "Tpl_ContinuousWaterBalance",
     "InternalCoupling", "Lighter MIKE SHE set-up: the saturated zone as linear reservoirs instead of the 3D finite-difference model; river in MIKE 11.",
     [("Penman-Monteih", ["Role_PET"], "MIKESHE"), ("RichardsEquation", ["Role_SoilWaterBudget", "Role_ExcessRainfall"], "MIKESHE"),
      ("DiffusiveWave2D", ["Role_RunoffTransform"], "MIKESHE"), ("LinearReservoir", ["Role_Baseflow"], "MIKESHE"),
      ("Saint-VenantEquations1D", ["Role_ChannelRouting"], "MIKE11")]),
    ("RC_SWAT_GreenAmpt_SubDaily", "SWAT sub-daily event flood", "Tpl_EventFloodHydrograph",
     "InternalCoupling", "SWAT run at a sub-daily step: Green-Ampt infiltration and the sub-daily unit hydrograph, Muskingum routing.",
     [("Green-Ampt", ["Role_ExcessRainfall"], "SWAT"), ("SCS-UH", ["Role_RunoffTransform"], "SWAT"),
      ("Muskingum-Cunge", ["Role_ChannelRouting"], "SWAT")]),
    ("RC_SWAT_WaterQuality", "SWAT catchment water quality", "Tpl_UrbanWaterQuality",
     "InternalCoupling", "Nutrient and pollutant loads from the land phase of SWAT, routed in the channels.",
     [("SCS-CN", ["Role_ExcessRainfall"], "SWAT"), ("ConceptualRoutingReservoir", ["Role_RunoffTransform"], "SWAT"),
      ("PollutantBuildupWashoff", ["Role_PollutantLoading"], "SWAT"), ("Muskingum-Cunge", ["Role_ChannelRouting"], "SWAT")]),
    ("RC_SWMM_UrbanDrainage", "SWMM urban drainage (dynamic wave)", "Tpl_EventFloodHydrograph",
     "InternalCoupling", "Urban runoff on subcatchments and dynamic-wave routing in pipes and open channels.",
     [("HortonInfiltrationModel", ["Role_ExcessRainfall"], "SWMM"), ("NonLinearReservoir", ["Role_RunoffTransform"], "SWMM"),
      ("Saint-VenantEquations1D", ["Role_ChannelRouting"], "SWMM")]),
    ("RC_SWMM_Iber_DualDrainage", "SWMM + Iber 2D dual drainage (open source)", "Tpl_FloodInundation",
     "TwoWayCoupling", "Sewer network in SWMM exchanging with 2D surface flow in Iber at the manholes: urban flood extent and depths.",
     [("HortonInfiltrationModel", ["Role_ExcessRainfall"], "SWMM"), ("NonLinearReservoir", ["Role_RunoffTransform"], "SWMM"),
      ("Saint-VenantEquations1D", ["Role_ChannelRouting"], "SWMM"), ("ShallowWaterEquations2D", ["Role_Hydraulics"], "IberPlus")]),
    ("RC_SWMM_TELEMAC2D_DualDrainage", "SWMM + TELEMAC-2D dual drainage", "Tpl_FloodInundation",
     "TwoWayCoupling", "Sewer network in SWMM coupled to TELEMAC-2D surface flow for urban waterlogging and river overflow.",
     [("HortonInfiltrationModel", ["Role_ExcessRainfall"], "SWMM"), ("NonLinearReservoir", ["Role_RunoffTransform"], "SWMM"),
      ("Saint-VenantEquations1D", ["Role_ChannelRouting"], "SWMM"), ("ShallowWaterEquations2D", ["Role_Hydraulics"], "TELEMAC-2D")]),
    ("RC_TELEMAC2D_GAIA", "TELEMAC-2D + GAIA morphodynamics", "Tpl_Morphodynamics",
     "InternalCoupling", "2D hydrodynamics coupled online to GAIA for bedload, suspended load and bed evolution.",
     [("ShallowWaterEquations2D", ["Role_Hydraulics"], "TELEMAC-2D"),
      ("FiniteVolumeSedimentTransport", ["Role_SedimentTransport", "Role_Morphology"], "TELEMAC")]),
]

# The two facts this script used to add about core methods (Clark-UH continuous, SCS-CN in
# HEC-RAS) are core knowledge: since 0.9.0 they are in aio-additions.ttl.


def lit(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"@en'


def safe(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text)


def build(processes: dict[str, list[str]] | None = None) -> str:
    out = ["""@prefix : <https://w3id.org/aio#> .
@prefix aiosw: <https://w3id.org/aio/software#> .
@prefix aiowf: <https://w3id.org/aio/workflow#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

#################################################################
#    Software modules and usual workflows - DRAFT FOR EXPERT VALIDATION
#    Generated by build_software_ttl.py: edit the tables there, not this file.
#################################################################

aiosw:SoftwareModule rdf:type owl:Class ;
    rdfs:label "software module"@en ;
    skos:definition "The implementation of one method inside one software (e.g. the MIKE SHE unsaturated-zone module using Richards equation), with the time step and spatial resolution it is usually run at in that software."@en .

aiosw:moduleOf rdf:type owl:ObjectProperty , owl:FunctionalProperty ;
    rdfs:domain aiosw:SoftwareModule ; rdfs:range :SoftwarePlatform ; rdfs:label "module of"@en .
aiosw:implementsMethod rdf:type owl:ObjectProperty , owl:FunctionalProperty ;
    rdfs:domain aiosw:SoftwareModule ; rdfs:range :ModelingMethod ; rdfs:label "implements method"@en .
aiosw:moduleName rdf:type owl:DatatypeProperty ; rdfs:domain aiosw:SoftwareModule ; rdfs:label "module name"@en .
aiosw:moduleTimeStep rdf:type owl:DatatypeProperty ; rdfs:domain aiosw:SoftwareModule ;
    rdfs:label "module time step"@en ; skos:definition "Time step usually used for this module in this software, as text."@en .
aiosw:moduleTimeStepClass rdf:type owl:ObjectProperty ; rdfs:domain aiosw:SoftwareModule ; rdfs:range :TimeStepClass ;
    rdfs:label "module time-step class"@en .
aiosw:moduleSpatialUnit rdf:type owl:DatatypeProperty ; rdfs:domain aiosw:SoftwareModule ;
    rdfs:label "module spatial unit"@en ; skos:definition "The computational unit: subbasin, HRU, grid cell, mesh element, cross-section..."@en .
aiosw:moduleResolution rdf:type owl:DatatypeProperty ; rdfs:domain aiosw:SoftwareModule ;
    rdfs:label "module spatial resolution"@en ; skos:definition "Usual size of the computational unit in practice, as text."@en .
"""]
    out.append("")
    for (software, method), (module, step, classes, unit, resolution) in sorted(MODULES.items()):
        node = f"aiosw:Module_{safe(software)}_{safe(method)}"
        out.append(f"""{node} rdf:type owl:NamedIndividual , aiosw:SoftwareModule ;
    aiosw:moduleOf :{software} ; aiosw:implementsMethod :{method} ;
    aiosw:moduleName {lit(module)} ;
    aiosw:moduleTimeStep {lit(step)} ;
    aiosw:moduleTimeStepClass {", ".join(":" + c for c in classes)} ;
    aiosw:moduleSpatialUnit {lit(unit)} ;
    aiosw:moduleResolution {lit(resolution)} ;
    rdfs:label {lit(f"{module} ({software})")} .
""")
    for chain_id, label, template, coupling, note, steps in CHAINS:
        software = sorted({s for _, _, s in steps})
        covers = sorted({p for method, _, _ in steps for p in (processes or {}).get(method, [])})
        step_nodes = []
        order = 0
        body = []
        for method, roles, sw in steps:
            for role in roles:
                order += 1
                node = f"aiosw:{chain_id}_S{order}"
                step_nodes.append(node)
                body.append(f"""{node} rdf:type owl:NamedIndividual , aiosw:ChainStep ;
    aiosw:usesMethod :{method} ; aiosw:stepRole aiowf:{role} ; aiosw:stepSoftware :{sw} ; aiosw:stepOrder {order} ;
    rdfs:label {lit(f"{label} – {order}: {method}")} .
""")
        out.append(f"""aiosw:{chain_id} rdf:type owl:NamedIndividual , aiosw:ReferenceChain ;
    rdfs:label {lit(label)} ;
    skos:note {lit(note + " Draft for expert validation.")} ;
    aiosw:instantiatesTemplate aiowf:{template} ;
    aiosw:hasCouplingType aiowf:{coupling} ;
    aiosw:chainUsesSoftware {", ".join(":" + s for s in software)} ;
{"    aiosw:coversProcess " + ", ".join(":" + p for p in covers) + " ;" if covers else ""}
    aiosw:hasStep {", ".join(step_nodes)} .
""")
        out.extend(body)
    return "\n".join(out)


if __name__ == "__main__":
    import json
    import sys

    # processes of each method, given as JSON on stdin by the backend helper, or none
    processes = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    (HERE / "aio-software-generated.ttl").write_text(build(processes), encoding="utf-8")
    print("written", HERE / "aio-software-generated.ttl", len(MODULES), "modules,", len(CHAINS), "workflows")
