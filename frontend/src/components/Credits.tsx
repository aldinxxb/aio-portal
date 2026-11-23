import { useState } from "react";

// Who made the portal, and who supports it: three columns, each with its title on top and
// its logos on one line below. The logos come from the project's integration plan and live
// in public/partners/; while a file is missing, the partner's name is shown in its place.
type Partner = { name: string; logo: string; url: string };

const DEVELOPED_BY: Partner[] = [
  { name: "Géoazur", logo: "/partners/geoazur.png", url: "https://geoazur.oca.eu/" },
  { name: "Université Côte d'Azur – IMREDD, Institut d'innovation et de partenariats", logo: "/partners/uca-imredd.png", url: "https://imredd.fr/" },
];
const PARTNERS: Partner[] = [
  { name: "Métropole Nice Côte d'Azur – eau et assainissement", logo: "/partners/metropole-nca.png", url: "https://www.nicecotedazur.org/" },
  { name: "Xylem", logo: "/partners/xylem.png", url: "https://www.xylem.com/" },
  { name: "République française – ADEME, Agence de la transition écologique", logo: "/partners/ademe-rf.png", url: "https://www.ademe.fr/" },
];

function Logo({ name, logo, url }: Partner) {
  const [missing, setMissing] = useState(false);
  return (
    <a className="partner" href={url} target="_blank" rel="noreferrer" title={name}>
      {missing ? <span className="partner-name">{name}</span> : <img src={logo} alt={name} onError={() => setMissing(true)} />}
    </a>
  );
}

function Group({ title, partners }: { title: string; partners: Partner[] }) {
  return (
    <div className="credits-col">
      <div className="credits-label">{title}</div>
      <div className="credits-logos">{partners.map((p) => <Logo key={p.name} {...p} />)}</div>
    </div>
  );
}

export default function Credits() {
  return (
    <footer className="credits">
      <div className="credits-col credits-project">
        <div className="credits-label">A project of</div>
        <div className="credits-logos">
          <img src="/aio-logo.png" alt="AIO – Agir et Innover pour l'Eau" />
          <span className="credits-text">Hydrology Decision Support<br />ontology-driven model and open-data recommendation</span>
        </div>
      </div>
      <Group title="Developed by" partners={DEVELOPED_BY} />
      <Group title="Partners & funding" partners={PARTNERS} />
    </footer>
  );
}
