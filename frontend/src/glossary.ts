// The technical words of the portal, explained where they appear (see components/Def.tsx).
//
// Each entry has a short definition in plain words and the AIO ontology term it belongs to.
// When the ontology defines the term itself well, `fromOntology` also quotes that definition,
// so the portal and the ontology say the same thing. The link opens the term in the ontology.

export type GlossaryEntry = {
  label: string;          // the word, as shown at the top of the explanation
  text: string;           // plain words, always shown first
  term: string | null;    // the AIO ontology term to open
  fromOntology?: boolean; // also quote the ontology's own definition of `term`
};

export const GLOSSARY = {
  forcing: {
    label: "Forcing",
    text: "A time-varying input that drives the model from outside, such as rainfall, air temperature or radiation. It must cover the whole simulated period.",
    term: "drivesProcess",
  },
  boundary: {
    label: "Boundary condition",
    text: "What enters or leaves the modelled area at its limits: a discharge flowing in upstream, a sea level downstream, a groundwater flux at the edge.",
    term: "BoundaryCompartment",
  },
  static: {
    label: "Static description",
    text: "A property of the site that hardly changes during the study: terrain, soil, geology, land cover, and the model parameters derived from them.",
    term: "ParameterVariable",
    fromOntology: true,
  },
  calibration: {
    label: "Calibration",
    text: "Tuning a model's free parameters so that its results match observations (often measured discharge), then checking it on another period.",
    term: "hasCalibrationParameter",
  },
  initial: {
    label: "Initial state",
    text: "The state of the system when the run starts (soil moisture, groundwater heads, snow…), taken from a warm-up run or an observed snapshot.",
    term: "requiresInitialCondition",
  },
  standard: {
    label: "Standard practice",
    text: "A combination of methods commonly used together, in named software, for this kind of study.",
    term: "ReferenceChain",
    fromOntology: true,
  },
  generated: {
    label: "Possible combination",
    text: "A chain of methods built by the portal from the ontology (each step does one job and passes its results to the next). It is coherent on paper but less proven than a standard workflow.",
    term: "ChainTemplate",
  },
  coupling: {
    label: "Coupling",
    text: "How two models exchange information: one after the other (one-way), or both during the run (two-way).",
    term: "CouplingType",
  },
  hru: {
    label: "HRU",
    text: "Hydrological response unit: an area with the same land use, soil and slope, computed as one unit (used by SWAT). A semi-distributed representation.",
    term: "SemiDistributed",
  },
  timestep: {
    label: "Time step",
    text: "How often the model computes its state: sub-hourly, hourly, daily… Input data should be at this step or finer.",
    term: "TimeStepClass",
  },
  opendata: {
    label: "Open data",
    text: "Datasets anyone can download and reuse (Météo-France, Sandre, IGN, Copernicus…). The portal lists those covering your area for each input.",
    term: "dcat:Dataset",
  },
} satisfies Record<string, GlossaryEntry>;

export type GlossaryKey = keyof typeof GLOSSARY;
