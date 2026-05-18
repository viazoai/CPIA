import { TopBar } from "@/app/components/TopBar";
import { Sidebar } from "@/app/components/Sidebar";
import { Toaster } from "@/components/ui/sonner";

export default function AppShellLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <>
      <TopBar />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 min-w-0">{children}</main>
      </div>
      <Toaster richColors position="top-right" />
    </>
  );
}
