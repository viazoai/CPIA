"use client";
/* 작업일보 업로드 다이얼로그.
 * - 폴더 선택 / 파일 선택 / 드래그 앤 드롭 지원
 * - 추가된 파일을 리스트로 보여주고 갯수 표시
 * - 제출 시 /api/upload 로 multipart POST → data/upload/<timestamp>/<file> 저장 */
import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Upload, FolderOpen, FileText, X, Loader2, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUploaded?: (result: { count: number; folder: string }) => void;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function fileKey(f: File): string {
  // 같은 이름 + 같은 크기 + 같은 lastModified 면 동일 파일로 간주.
  return `${f.name}_${f.size}_${f.lastModified}`;
}

export function UploadDailyReportDialog({ open, onOpenChange, onUploaded }: Props) {
  const [files, setFiles] = React.useState<File[]>([]);
  const [dragOver, setDragOver] = React.useState(false);
  const [status, setStatus] = React.useState<"idle" | "uploading" | "done" | "error">("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<{ count: number; folder: string } | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const folderInputRef = React.useRef<HTMLInputElement | null>(null);

  // 다이얼로그 닫힐 때 상태 초기화.
  React.useEffect(() => {
    if (!open) {
      const t = setTimeout(() => {
        setFiles([]);
        setStatus("idle");
        setError(null);
        setResult(null);
        setDragOver(false);
      }, 200);
      return () => clearTimeout(t);
    }
  }, [open]);

  const addFiles = (incoming: FileList | File[]) => {
    const list = Array.from(incoming);
    setFiles((prev) => {
      const seen = new Set(prev.map(fileKey));
      const fresh = list.filter((f) => !seen.has(fileKey(f)));
      return [...prev, ...fresh];
    });
  };

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };
  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer?.files) addFiles(e.dataTransfer.files);
  };

  const onSubmit = async () => {
    if (files.length === 0 || status === "uploading") return;
    setStatus("uploading");
    setError(null);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f, f.name));
      const res = await fetch("/api/upload", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data?.error ?? `HTTP ${res.status}`);
      setStatus("done");
      setResult({ count: data.count, folder: data.folder });
      onUploaded?.({ count: data.count, folder: data.folder });
    } catch (e: any) {
      setStatus("error");
      setError(e?.message ?? "업로드 실패");
    }
  };

  const totalBytes = files.reduce((s, f) => s + f.size, 0);
  const canSubmit = files.length > 0 && status !== "uploading" && status !== "done";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl gap-0 p-0">
        <DialogHeader className="border-b border-border-soft px-6 py-5">
          <DialogTitle className="text-base font-semibold tracking-tight text-ink">
            작업일보 업로드
          </DialogTitle>
          <DialogDescription className="text-xs text-ink-mid">
            업체별 일단위 작업일보 파일을 드래그하거나 폴더에서 선택해 업로드합니다.
          </DialogDescription>
        </DialogHeader>

        <div className="px-6 py-5">
          {/* 드롭 존 */}
          <div
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            className={cn(
              "relative flex flex-col items-center justify-center rounded-card border-2 border-dashed px-6 py-10 transition-colors",
              dragOver
                ? "border-brand-deep bg-brand/30"
                : "border-border bg-bg-soft/40 hover:bg-bg-soft",
            )}
          >
            <Upload className={cn("h-8 w-8 transition-colors", dragOver ? "text-brand-deep" : "text-ink-light")} />
            <p className="mt-3 text-sm font-medium text-ink">
              파일을 이곳에 드래그하거나
            </p>
            <p className="mt-1 text-xs text-ink-mid">
              아래 버튼으로 폴더 또는 개별 파일을 선택하세요
            </p>

            <div className="mt-4 flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                className="h-8 gap-1.5 text-xs"
              >
                <FileText className="h-3.5 w-3.5" />
                파일 선택
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => folderInputRef.current?.click()}
                className="h-8 gap-1.5 text-xs"
              >
                <FolderOpen className="h-3.5 w-3.5" />
                폴더 선택
              </Button>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files);
                e.target.value = "";
              }}
            />
            <input
              ref={folderInputRef}
              type="file"
              multiple
              hidden
              // webkitdirectory: 폴더 picker (Chrome/Edge/Safari).
              // @ts-ignore — React 타입에 webkitdirectory 가 없음.
              webkitdirectory=""
              directory=""
              onChange={(e) => {
                if (e.target.files) addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>

          {/* 파일 리스트 */}
          {files.length > 0 && (
            <div className="mt-5">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-xs font-medium text-ink">
                  업로드 대기 <span className="font-mono text-brand-text">{files.length}</span>건
                  <span className="ml-2 text-ink-light">· 총 {formatBytes(totalBytes)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setFiles([])}
                  disabled={status === "uploading" || status === "done"}
                  className="text-[11px] text-ink-light hover:text-ink disabled:opacity-40"
                >
                  전체 비우기
                </button>
              </div>

              <ul className="max-h-56 overflow-y-auto rounded-card border border-border-soft divide-y divide-border-soft">
                {files.map((f, idx) => (
                  <li
                    key={`${fileKey(f)}_${idx}`}
                    className="flex items-center gap-3 bg-card px-3 py-2"
                  >
                    <FileText className="h-3.5 w-3.5 shrink-0 text-ink-light" />
                    <div className="flex-1 min-w-0">
                      <div className="truncate text-xs font-medium text-ink">{f.name}</div>
                      <div className="text-[10px] text-ink-light">{formatBytes(f.size)}</div>
                    </div>
                    {status !== "done" && (
                      <button
                        type="button"
                        onClick={() => removeFile(idx)}
                        disabled={status === "uploading"}
                        className="rounded p-1 text-ink-light hover:bg-bg-soft hover:text-ink disabled:opacity-40"
                        aria-label={`${f.name} 제거`}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 상태 메시지 */}
          {status === "done" && result && (
            <div className="mt-4 flex items-start gap-2 rounded-card border border-mint-deep/30 bg-mint/40 px-3 py-2 text-xs text-mint-text">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <div className="font-medium">
                  업로드 완료 — {result.count}건
                </div>
                <div className="mt-0.5 font-mono text-[11px] opacity-80">
                  {result.folder}
                </div>
              </div>
            </div>
          )}
          {status === "error" && error && (
            <div className="mt-4 rounded-card border border-rose-deep/30 bg-rose/40 px-3 py-2 text-xs text-rose-text">
              업로드 실패: {error}
            </div>
          )}
        </div>

        <DialogFooter className="border-t border-border-soft bg-bg-soft/40 px-6 py-4">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="h-9"
          >
            {status === "done" ? "닫기" : "취소"}
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={onSubmit}
            disabled={!canSubmit}
            className="h-9 gap-1.5"
          >
            {status === "uploading" ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                업로드 중…
              </>
            ) : status === "done" ? (
              <>
                <CheckCircle2 className="h-3.5 w-3.5" />
                완료
              </>
            ) : (
              <>
                <Upload className="h-3.5 w-3.5" />
                제출 {files.length > 0 && `(${files.length})`}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
