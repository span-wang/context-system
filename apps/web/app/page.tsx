import { headers } from "next/headers";
import { redirect } from "next/navigation";

export default async function Home() {
  const headerStore = await headers();
  const host = headerStore.get("x-forwarded-host") || headerStore.get("host") || "";

  if (host.includes("context.panspan.cloud")) {
    redirect("/platform");
  }

  redirect("/workflow");
}
