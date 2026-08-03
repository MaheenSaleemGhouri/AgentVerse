"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  listMyDevicesAction,
  revokeDeviceAction,
  setPasswordPolicyAction,
} from "@/lib/api/actions";
import type { TrustedDevice, UpdatePasswordPolicyRequest } from "@/lib/api/security";
import { queryKeys } from "@/lib/queries/keys";

export function useMyDevices(initialData?: TrustedDevice[]) {
  return useQuery({
    queryKey: queryKeys.myDevices(),
    queryFn: () => listMyDevicesAction(),
    ...(initialData ? { initialData } : {}),
  });
}

export function useRevokeDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: string) => revokeDeviceAction(deviceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.myDevices() });
      // Says what actually happens next, rather than a bare "Revoked":
      // the device is not signed out, it just stops being recognised.
      toast.success("Device revoked. Signing in from it will be reported as new.");
    },
    onError: () => toast.error("Could not revoke that device."),
  });
}

export function useSetPasswordPolicy(organizationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdatePasswordPolicyRequest) =>
      setPasswordPolicyAction(organizationId, body),
    onSuccess: (policy) => {
      queryClient.setQueryData(queryKeys.passwordPolicy(organizationId), policy);
      toast.success("Password policy saved.");
    },
    onError: () => toast.error("Could not save the password policy."),
  });
}
