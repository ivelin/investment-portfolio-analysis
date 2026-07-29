import { Outlet, createFileRoute } from "@tanstack/react-router";

/**
 * Layout for /connectors and /connectors/setup/$broker.
 * Child routes render via Outlet (list or setup guide).
 */
export const Route = createFileRoute("/connectors")({
  component: ConnectorsLayout,
});

function ConnectorsLayout() {
  return <Outlet />;
}
