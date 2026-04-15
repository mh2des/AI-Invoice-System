"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  getCurrentUser,
  loginUser,
  registerUser,
  type AuthUser,
} from "@/lib/api";
import { clearTokens, getAccessToken, setTokens } from "@/lib/auth";

import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";

// ── Context ──

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

// ── Provider ──

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  const fetchUser = useCallback(async () => {
    try {
      const data = await getCurrentUser();
      setUser(data);
    } catch {
      clearTokens();
      setUser(null);
    }
  }, []);

  useEffect(() => {
    const token = getAccessToken();
    if (token) {
      fetchUser().finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, [fetchUser]);

  const login = async (email: string, password: string) => {
    const tokens = await loginUser(email, password);
    setTokens(tokens.access_token, tokens.refresh_token);
    await fetchUser();
  };

  const register = async (
    email: string,
    password: string,
    fullName: string
  ) => {
    await registerUser(email, password, fullName);
    // Auto-login after registration
    const tokens = await loginUser(email, password);
    setTokens(tokens.access_token, tokens.refresh_token);
    await fetchUser();
  };

  const logout = () => {
    clearTokens();
    setUser(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ── App Shell (conditional sidebar) ──

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { isAuthenticated, isLoading, logout, user } = useAuth();
  const router = useRouter();

  // Login page — render without sidebar
  if (pathname === "/login") {
    return <>{children}</>;
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  // Not authenticated — redirect to login
  if (!isAuthenticated) {
    router.push("/login");
    return null;
  }

  // Authenticated — show app with sidebar
  return (
    <TooltipProvider>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4 md:px-6">
            <SidebarTrigger className="-ml-1" />
            <Separator orientation="vertical" className="mr-2 h-4" />
            <span className="text-sm font-medium text-muted-foreground">
              AI Invoice Processing System
            </span>
            <div className="ml-auto flex items-center gap-3">
              <span className="text-sm text-muted-foreground">
                {user?.full_name}
              </span>
              <button
                onClick={logout}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                Sign out
              </button>
            </div>
          </header>
          <main className="flex-1 overflow-auto">{children}</main>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  );
}
