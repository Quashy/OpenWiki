import { Alert, Button, Card, CardBody, CardHeader, Chip, Input, Select, SelectItem, Tab, Tabs } from "@heroui/react";
import { useMutation } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { FormEvent, Key, useState } from "react";

import { login, register } from "../api/m1";
import { demoAccounts, firstKey } from "../app/navigation";
import { useAuthStore } from "../stores/authStore";

export function LoginView() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("password123");
  const [error, setError] = useState("");
  const setAuth = useAuthStore((state) => state.setAuth);
  const authMutation = useMutation({
    mutationFn: () => (mode === "login" ? login({ username, password }) : register({ username, password })),
    onSuccess: (data) => {
      setError("");
      setAuth(data);
    },
    onError: () => setError(mode === "login" ? "登录失败，请检查账号密码" : "注册失败，请检查用户名是否已存在"),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    authMutation.mutate();
  }

  function selectDemoAccount(keys: "all" | Iterable<Key>) {
    const nextUsername = firstKey(keys, "admin");
    const account = demoAccounts.find((item) => item.username === nextUsername);
    if (!account) return;
    setMode("login");
    setUsername(account.username);
    setPassword(account.password);
  }

  return (
    <main className="min-h-screen bg-default-50 px-4 py-10 text-foreground">
      <div className="mx-auto grid min-h-[calc(100vh-5rem)] w-full max-w-5xl items-center gap-8 lg:grid-cols-[1fr_420px]">
        <section className="hidden lg:block">
          <div className="mb-8 flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-lg bg-primary text-primary-foreground">
              <ShieldCheck size={24} aria-hidden="true" />
            </span>
            <div>
              <h1 className="text-2xl font-semibold">OpenWiki V2</h1>
              <p className="text-sm text-default-500">企业内部知识库系统</p>
            </div>
          </div>
          <Card shadow="sm">
            <CardBody className="gap-4 p-6">
              <Chip color="primary" variant="flat">
                M1 工作台
              </Chip>
              <h2 className="max-w-xl text-3xl font-semibold leading-tight">账号、团队、模型配置与知识库骨架已接入真实接口</h2>
              <p className="max-w-lg text-sm leading-6 text-default-500">
                登录后进入原型同款信息架构：知识库、Wiki 浏览器、图谱、问答、成员、模型设置与审计日志。
              </p>
            </CardBody>
          </Card>
        </section>

        <Card className="w-full" shadow="md">
          <CardHeader className="flex-col items-start gap-2 px-7 pt-7">
            <div className="flex items-center gap-3 lg:hidden">
              <span className="grid size-10 place-items-center rounded-lg bg-primary text-primary-foreground">
                <ShieldCheck size={22} aria-hidden="true" />
              </span>
              <h1 className="text-xl font-semibold">OpenWiki V2</h1>
            </div>
            <div>
              <h2 className="text-xl font-semibold">{mode === "login" ? "登录" : "注册"}</h2>
              <p className="mt-1 text-sm text-default-500">企业内部 LLM Wiki 知识库系统</p>
            </div>
          </CardHeader>
          <CardBody className="gap-5 px-7 pb-7">
            <Tabs selectedKey={mode} onSelectionChange={(key) => setMode(String(key) as "login" | "register")} aria-label="认证方式">
              <Tab key="login" title="登录" />
              <Tab key="register" title="注册" />
            </Tabs>
            <Select label="验收账号" selectedKeys={new Set([username])} onSelectionChange={selectDemoAccount}>
              {demoAccounts.map((account) => (
                <SelectItem key={account.username}>{account.label}</SelectItem>
              ))}
            </Select>
            <form className="grid gap-4" onSubmit={submit}>
              <Input label="用户名" autoComplete="username" value={username} onValueChange={setUsername} isRequired minLength={3} />
              <Input
                label="密码"
                type="password"
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                value={password}
                onValueChange={setPassword}
                isRequired
                minLength={8}
              />
              {error ? (
                <Alert color="danger" variant="flat">
                  {error}
                </Alert>
              ) : null}
              <Button color="primary" type="submit" isLoading={authMutation.isPending}>
                {mode === "login" ? "登录" : "注册并进入"}
              </Button>
            </form>
          </CardBody>
        </Card>
      </div>
    </main>
  );
}
