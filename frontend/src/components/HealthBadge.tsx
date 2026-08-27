import { Button } from "@heroui/react";
import { RefreshCw, Wifi, WifiOff } from "lucide-react";
import { useHealth } from "../lib/useHealth";

export function HealthBadge() {
  const { data, isError, isFetching, refetch } = useHealth();
  const online = data?.status === "ok" && !isError;

  return (
    <div className="flex items-center gap-2">
      <div className="flex h-10 items-center gap-2 border border-[#d8d2c6] bg-white px-3 text-sm">
        {online ? <Wifi size={16} /> : <WifiOff size={16} />}
        <span>{online ? "Backend online" : "Backend offline"}</span>
      </div>
      <Button
        isIconOnly
        aria-label="刷新后端状态"
        className="h-10 min-w-10 rounded-none border border-[#d8d2c6] bg-white text-[#1d2524]"
        isLoading={isFetching}
        onPress={() => void refetch()}
        variant="bordered"
      >
        <RefreshCw size={16} />
      </Button>
    </div>
  );
}

