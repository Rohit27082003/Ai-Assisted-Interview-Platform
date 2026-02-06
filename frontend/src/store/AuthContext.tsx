import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';

interface User {
    sub: string;
    email: string;
    name: string;
}

interface AuthTokens {
    accessToken: string;
    idToken?: string;
    refreshToken?: string;
    expiresIn: number;
}

interface AuthContextType {
    user: User | null;
    tokens: AuthTokens | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    login: (email: string, password: string) => Promise<void>;
    logout: () => void;
    refreshAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const STORAGE_KEYS = {
    TOKENS: 'auth_tokens',
    USER: 'auth_user',
};

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [tokens, setTokens] = useState<AuthTokens | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    // Load auth state from localStorage on mount
    useEffect(() => {
        const storedTokens = localStorage.getItem(STORAGE_KEYS.TOKENS);
        const storedUser = localStorage.getItem(STORAGE_KEYS.USER);

        if (storedTokens && storedUser) {
            try {
                setTokens(JSON.parse(storedTokens));
                setUser(JSON.parse(storedUser));
            } catch {
                // Clear invalid data
                localStorage.removeItem(STORAGE_KEYS.TOKENS);
                localStorage.removeItem(STORAGE_KEYS.USER);
            }
        }
        setIsLoading(false);
    }, []);

    const login = useCallback(async (email: string, password: string) => {
        setIsLoading(true);
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Login failed');
            }

            const tokenData = await response.json();
            const newTokens: AuthTokens = {
                accessToken: tokenData.access_token,
                idToken: tokenData.id_token,
                refreshToken: tokenData.refresh_token,
                expiresIn: tokenData.expires_in,
            };

            // Store tokens
            setTokens(newTokens);
            localStorage.setItem(STORAGE_KEYS.TOKENS, JSON.stringify(newTokens));

            // Fetch user info
            const userResponse = await fetch('/api/auth/me', {
                headers: { Authorization: `Bearer ${newTokens.accessToken}` },
            });

            if (userResponse.ok) {
                const userData = await userResponse.json();
                setUser(userData);
                localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(userData));
            }
        } finally {
            setIsLoading(false);
        }
    }, []);

    const logout = useCallback(async () => {
        // We can't easily access current tokens here due to closure, 
        // but we can read from state or storage if needed. 
        // For simplicity, just clear everything.
        const storedTokens = localStorage.getItem(STORAGE_KEYS.TOKENS);
        if (storedTokens) {
            try {
                const t = JSON.parse(storedTokens);
                if (t.accessToken) {
                    await fetch('/api/auth/logout', {
                        method: 'POST',
                        headers: { Authorization: `Bearer ${t.accessToken}` },
                    });
                }
            } catch {
                // Ignore
            }
        }

        setUser(null);
        setTokens(null);
        localStorage.removeItem(STORAGE_KEYS.TOKENS);
        localStorage.removeItem(STORAGE_KEYS.USER);
    }, []);

    const refreshAuth = useCallback(async () => {
        const storedTokens = localStorage.getItem(STORAGE_KEYS.TOKENS);
        if (!storedTokens) return;

        try {
            const currentTokens = JSON.parse(storedTokens);
            if (!currentTokens.refreshToken) return;

            const response = await fetch('/api/auth/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: currentTokens.refreshToken }),
            });

            if (response.ok) {
                const tokenData = await response.json();
                const newTokens: AuthTokens = {
                    ...currentTokens,
                    accessToken: tokenData.access_token,
                    idToken: tokenData.id_token,
                    expiresIn: tokenData.expires_in,
                };
                setTokens(newTokens);
                localStorage.setItem(STORAGE_KEYS.TOKENS, JSON.stringify(newTokens));
            } else {
                // Refresh failed, logout
                logout();
            }
        } catch {
            logout();
        }
    }, [logout]);

    // Global event listener for token expiry
    useEffect(() => {
        const handleUnauthorized = () => {
            logout();
        };
        window.addEventListener('auth:unauthorized', handleUnauthorized);
        return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
    }, [logout]);

    return (
        <AuthContext.Provider
            value={{
                user,
                tokens,
                isAuthenticated: !!user && !!tokens,
                isLoading,
                login,
                logout,
                refreshAuth,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}

// Helper to get auth header for API calls
export function getAuthHeader(): Record<string, string> {
    const storedTokens = localStorage.getItem(STORAGE_KEYS.TOKENS);
    if (!storedTokens) return {};

    try {
        const tokens = JSON.parse(storedTokens) as AuthTokens;
        return { Authorization: `Bearer ${tokens.accessToken}` };
    } catch {
        return {};
    }
}
