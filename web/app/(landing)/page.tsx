import { LandingNav } from "../components/landing/LandingNav";
import { LandingHero } from "../components/landing/LandingHero";
import { BackgroundSection } from "../components/landing/BackgroundSection";
import { AsIsToBeSection } from "../components/landing/AsIsToBeSection";
import { ImpactSection } from "../components/landing/ImpactSection";
import { ScalabilitySection } from "../components/landing/ScalabilitySection";
import { FinalCtaSection } from "../components/landing/FinalCtaSection";
import { LandingFooter } from "../components/landing/LandingFooter";

export default function LandingPage() {
  return (
    <>
      <LandingNav />
      <main>
        <LandingHero />
        <BackgroundSection />
        <AsIsToBeSection />
        <ImpactSection />
        <ScalabilitySection />
        <FinalCtaSection />
      </main>
      <LandingFooter />
    </>
  );
}
