import { LandingNav } from "../components/landing/LandingNav";
import { LandingHero } from "../components/landing/LandingHero";
import { BackgroundSection, BackgroundConstructionSection } from "../components/landing/BackgroundSection";
import { AsIsToBeSection } from "../components/landing/AsIsToBeSection";
import { CoreAiFeatureSlide } from "../components/landing/CoreAiSection";
import { ImpactSection, ImpactWorkloadSection, ImpactRedeploySection } from "../components/landing/ImpactSection";
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
          <BackgroundConstructionSection />
        </Slide>
        <Slide>
          <AsIsToBeSection />
        </Slide>
        <Slide>
          <CoreAiFeatureSlide index={0} />
        </Slide>
        <Slide>
          <CoreAiFeatureSlide index={1} />
        </Slide>
        <Slide>
          <CoreAiFeatureSlide index={2} />
        </Slide>
        <Slide>
          <ImpactSection />
        </Slide>
        <Slide>
          <ImpactWorkloadSection />
        </Slide>
        <Slide>
          <ImpactRedeploySection />
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
