import { LandingNav } from "../components/landing/LandingNav";
import { LandingHero } from "../components/landing/LandingHero";
import { BackgroundSection } from "../components/landing/BackgroundSection";
import { AsIsToBeSection } from "../components/landing/AsIsToBeSection";
import { CoreAiSection } from "../components/landing/CoreAiSection";
import { ImpactSection } from "../components/landing/ImpactSection";
import { ScalabilitySection } from "../components/landing/ScalabilitySection";
import { FinalCtaSection } from "../components/landing/FinalCtaSection";
import { PresentationShell } from "../components/landing/PresentationShell";
import { Slide } from "../components/landing/Slide";

/* 랜딩은 슬라이드 발표 모드로 동작.
 * 상단 LandingNav(64px) + 그 아래 PresentationShell(나머지 100vh-4rem). */
export default function LandingPage() {
  return (
    <>
      <LandingNav />
      <PresentationShell>
        <Slide>
          <LandingHero />
        </Slide>
        <Slide>
          <BackgroundSection />
        </Slide>
        <Slide>
          <AsIsToBeSection />
        </Slide>
        <Slide>
          <CoreAiSection />
        </Slide>
        <Slide>
          <ImpactSection />
        </Slide>
        <Slide>
          <ScalabilitySection />
        </Slide>
        <Slide>
          <FinalCtaSection />
        </Slide>
      </PresentationShell>
    </>
  );
}
