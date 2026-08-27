import { AppShell } from "./components/AppShell";
import { LoginView } from "./components/LoginView";
import { useAuthStore } from "./stores/authStore";

function App() {
  const user = useAuthStore((state) => state.user);
  return user ? <AppShell /> : <LoginView />;
}

export default App;
