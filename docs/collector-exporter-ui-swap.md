# B_Track UI Swap — `ConsolidatedReportCard.tsx`

> Exporter FastAPI endpoint 준비 완료 (`GET /export/run?site_id&date`).
> B_Track 이 fallback (docs/sample 다운로드) 를 실 endpoint 호출로 교체.

## 변경 위치

`web/app/components/export/ConsolidatedReportCard.tsx:38~59` 의 `handleExport`.

## 변경 전 (현재 — fallback)

```typescript
const handleExport = async () => {
  if (busy) return;
  setBusy(true);
  const id = toast.loading(`Exporter 에이전트 작동 중…`);
  try {
    await new Promise((r) => setTimeout(r, 1500));
    const a = document.createElement("a");
    a.href = "/sample/cpia-consolidated-report.xlsx";
    a.download = `통합작업일보_${report.date}.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    toast.success(`통합 작업일보 다운로드 완료`);
  } catch {
    toast.error("Exporter 실행에 실패했습니다.");
  } finally {
    setBusy(false);
  }
};
```

## 변경 후 (실 endpoint)

`NEXT_PUBLIC_FASTAPI_BASE` env 추가 (예: `http://localhost:8000`).

```typescript
const handleExport = async () => {
  if (busy) return;
  setBusy(true);
  const id = toast.loading(`Exporter 에이전트 작동 중…`);
  try {
    const siteId = process.env.NEXT_PUBLIC_DEFAULT_SITE_ID || "m15x-ph3-ibl";
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_FASTAPI_BASE}/export/run?site_id=${siteId}&date=${report.date}`,
    );
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `통합작업일보_${report.date}.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success(`통합 작업일보 다운로드 완료`, { id });
  } catch (e) {
    toast.error(`Exporter 실행 실패: ${(e as Error).message}`, { id });
  } finally {
    setBusy(false);
  }
};
```

## .env.local.example 추가

```bash
NEXT_PUBLIC_FASTAPI_BASE=http://localhost:8000
NEXT_PUBLIC_DEFAULT_SITE_ID=m15x-ph3-ibl
```

## BFF proxy 대안 (CORS / 인증 통일에 유리)

`web/app/api/export/[date]/route.ts` 신규 — Next.js BFF 가 FastAPI fetch 후 stream pipe. PoC 에선 직접 fetch 도 충분.

## 디자인 불가침 (memory: feedback_no_design_change)

본 swap 은 `handleExport` 내부 로직만 교체. 컴포넌트의 markup / className / Tailwind 클래스 / Toaster 인터페이스는 그대로 유지. 시연자 의도 보존.
