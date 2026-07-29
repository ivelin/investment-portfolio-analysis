import {
  HeadContent,
  Outlet,
  Scripts,
  createRootRoute,
} from "@tanstack/react-router";
import { Toaster } from "sonner";

import appCss from "../styles.css?url";

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      {
        title: "Portfolio Analysis — hold yourself to the same standard",
      },
      {
        name: "description",
        content:
          "Measure your accounts like funds. Capital efficiency, keep/monitor/weed discipline, honest data only. Private workspaces with a sample portfolio to start.",
      },
    ],
    links: [{ rel: "stylesheet", href: appCss }],
  }),
  component: RootComponent,
});

function RootComponent() {
  return (
    <html lang="en" className="dark">
      <head>
        <HeadContent />
      </head>
      <body className="min-h-dvh bg-bg text-fg antialiased">
        <Outlet />
        <Toaster theme="dark" position="top-center" richColors closeButton />
        <Scripts />
      </body>
    </html>
  );
}
