import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { lazy, Suspense } from "react";
import { TabBar } from "./components/TabBar";
import { Button, Skeleton, ease } from "./components/ui";
import { AppProvider, useApp } from "./hooks/useApp";
import { BookingFlow } from "./booking/BookingFlow";
import { Gallery } from "./pages/Gallery";
import { Home } from "./pages/Home";
import { Profile } from "./pages/Profile";
import { Services } from "./pages/Services";

const AdminApp = lazy(() => import("./admin/AdminApp"));
const isAdminRoute = () => location.pathname.startsWith("/admin") || new URLSearchParams(location.search).has("admin");

function Loading() {
  return (
    <div className="page">
      <Skeleton className="mt-4 h-10 w-40" />
      <Skeleton className="mt-6 h-[440px] w-full rounded-[32px]" />
      <div className="mt-6 flex gap-3"><Skeleton className="h-48 w-40" /><Skeleton className="h-48 w-40" /></div>
    </div>
  );
}

function ClientApp() {
  const { boot, error, tab, reload } = useApp();
  if (error) return (
    <div className="page flex min-h-[80vh] flex-col items-center justify-center text-center">
      <div className="h-display text-[34px]">Nail studio</div>
      <p className="mt-2 max-w-[280px] text-muted">{error}</p>
      <Button className="mt-6" onClick={reload}>Повторить</Button>
    </div>
  );
  if (!boot) return <Loading />;
  const Page = { home: Home, services: Services, book: BookingFlow, gallery: Gallery, me: Profile }[tab];
  return (
    <>
      <AnimatePresence mode="wait" initial={false}>
        <motion.main key={tab} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.32, ease }}>
          <Page />
        </motion.main>
      </AnimatePresence>
      <TabBar />
    </>
  );
}

export default function App() {
  return (
    <MotionConfig reducedMotion="user">
      <AppProvider>
        {isAdminRoute() ? <Suspense fallback={<Loading />}><AdminApp /></Suspense> : <ClientApp />}
      </AppProvider>
    </MotionConfig>
  );
}
