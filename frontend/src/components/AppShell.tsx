import {
  Avatar,
  Button,
  Chip,
  Dropdown,
  DropdownItem,
  DropdownMenu,
  DropdownTrigger,
  Input,
  Listbox,
  ListboxItem,
  ListboxSection,
  Modal,
  ModalBody,
  ModalContent,
  ModalFooter,
  ModalHeader,
  Navbar,
  NavbarBrand,
  NavbarContent,
  NavbarItem,
  NavbarMenu,
  NavbarMenuItem,
  NavbarMenuToggle,
  ScrollShadow,
} from "@heroui/react";
import { LogOut, ShieldCheck } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { updateCurrentWorkspace } from "../api/m1";
import { navSections, roleLabel, sectionTitle, type RouteKey } from "../app/navigation";
import { useAuthStore } from "../stores/authStore";
import { ChatPage } from "../pages/ChatPage";
import { KnowledgeBasePage } from "../pages/KnowledgeBasePage";
import { MembersPage } from "../pages/MembersPage";
import { MilestonePlaceholder } from "../pages/Placeholders";
import { SettingsPage } from "../pages/SettingsPage";
import { WikiBrowserPage } from "../pages/WikiBrowserPage";
import { WikiGraphPage } from "../pages/WikiGraphPage";

export function AppShell() {
  const [route, setRoute] = useState<RouteKey>("kbs");
  const [menuOpen, setMenuOpen] = useState(false);
  const [wikiKbId, setWikiKbId] = useState<string | null>(null);
  const [wikiPageId, setWikiPageId] = useState<string | null>(null);
  const { membership } = useAuthStore();
  const isAdmin = membership?.role === "admin";

  function selectRoute(nextRoute: RouteKey) {
    setRoute(nextRoute);
    setMenuOpen(false);
  }

  return (
    <div className="min-h-screen bg-default-50 text-foreground">
      <DesktopSidebar route={route} setRoute={selectRoute} isAdmin={isAdmin} />
      <div className="min-h-screen lg:pl-56">
        <MobileHeader route={route} setRoute={selectRoute} isAdmin={isAdmin} menuOpen={menuOpen} setMenuOpen={setMenuOpen} />
        <header className="sticky top-0 z-20 hidden h-14 items-center border-b border-divider bg-background/95 px-6 backdrop-blur lg:flex">
          <h2 className="text-sm font-semibold">{sectionTitle(route)}</h2>
          <div className="ml-auto flex items-center gap-3">
            <WorkspaceControl canManage={isAdmin} />
            <UserMenu />
          </div>
        </header>
        <main className="min-w-0 p-4 sm:p-6">
          {route === "kbs" && <KnowledgeBasePage canManage={isAdmin} onOpenWiki={(kbId) => { setWikiKbId(kbId); setRoute("wiki"); }} />}
          {route === "members" && <MembersPage />}
          {route === "settings" && <SettingsPage />}
          {route === "wiki" && <WikiBrowserPage initialKbId={wikiKbId} initialPageId={wikiPageId} />}
          {route === "graph" && <WikiGraphPage onOpenPage={(pageId) => { setWikiPageId(pageId); setRoute("wiki"); }} />}
          {route === "chat" && <ChatPage />}
          {route === "audit" && <MilestonePlaceholder title={sectionTitle(route)} route={route} />}
        </main>
      </div>
    </div>
  );
}

function WorkspaceControl({ canManage }: { canManage: boolean }) {
  const { workspace, setWorkspace } = useAuthStore();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(workspace?.name ?? "");
  const updateMutation = useMutation({
    mutationFn: () => updateCurrentWorkspace({ name }),
    onSuccess: (updatedWorkspace) => {
      setWorkspace(updatedWorkspace);
      setOpen(false);
    },
  });

  function openEditor() {
    setName(workspace?.name ?? "");
    setOpen(true);
  }

  if (!canManage || !workspace) {
    return <Chip variant="flat">{workspace?.name ?? "尚未加入团队"}</Chip>;
  }

  return (
    <>
      <Button size="sm" variant="flat" onPress={openEditor}>
        {workspace.name}
      </Button>
      <Modal isOpen={open} onOpenChange={setOpen} placement="center">
        <ModalContent>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              updateMutation.mutate();
            }}
          >
            <ModalHeader>编辑团队</ModalHeader>
            <ModalBody>
              <Input label="团队名称" value={name} onValueChange={setName} isRequired maxLength={128} />
              {updateMutation.isError ? <p className="text-sm text-danger">保存失败，请检查名称后重试。</p> : null}
            </ModalBody>
            <ModalFooter>
              <Button variant="light" onPress={() => setOpen(false)}>
                取消
              </Button>
              <Button color="primary" type="submit" isLoading={updateMutation.isPending}>
                保存
              </Button>
            </ModalFooter>
          </form>
        </ModalContent>
      </Modal>
    </>
  );
}

function DesktopSidebar({ route, setRoute, isAdmin }: { route: RouteKey; setRoute: (route: RouteKey) => void; isAdmin: boolean }) {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 flex-col border-r border-divider bg-background lg:flex">
      <div className="flex h-14 items-center gap-3 border-b border-divider px-5">
        <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">
          <ShieldCheck size={18} aria-hidden="true" />
        </span>
        <span className="font-semibold">OpenWiki V2</span>
      </div>
      <ScrollShadow className="min-h-0 flex-1 px-3 py-4">
        <SidebarNav route={route} setRoute={setRoute} isAdmin={isAdmin} />
      </ScrollShadow>
      <div className="border-t border-divider p-3">
        <UserMenu fullWidth />
      </div>
    </aside>
  );
}

function MobileHeader({
  route,
  setRoute,
  isAdmin,
  menuOpen,
  setMenuOpen,
}: {
  route: RouteKey;
  setRoute: (route: RouteKey) => void;
  isAdmin: boolean;
  menuOpen: boolean;
  setMenuOpen: (open: boolean) => void;
}) {
  return (
    <Navbar isBordered isMenuOpen={menuOpen} onMenuOpenChange={setMenuOpen} maxWidth="full" className="lg:hidden">
      <NavbarContent justify="start">
        <NavbarMenuToggle aria-label={menuOpen ? "关闭导航" : "打开导航"} />
        <NavbarBrand className="gap-3">
          <span className="grid size-8 place-items-center rounded-md bg-primary text-primary-foreground">
            <ShieldCheck size={18} aria-hidden="true" />
          </span>
          <span className="font-semibold">OpenWiki V2</span>
        </NavbarBrand>
      </NavbarContent>
      <NavbarContent justify="end">
        <NavbarItem>
          <UserMenu />
        </NavbarItem>
      </NavbarContent>
      <NavbarMenu className="pt-4">
        <NavbarMenuItem>
          <SidebarNav route={route} setRoute={setRoute} isAdmin={isAdmin} />
        </NavbarMenuItem>
      </NavbarMenu>
    </Navbar>
  );
}

function SidebarNav({ route, setRoute, isAdmin }: { route: RouteKey; setRoute: (route: RouteKey) => void; isAdmin: boolean }) {
  const sections = useMemo(
    () =>
      navSections
        .map((section) => ({
          ...section,
          items: section.items.filter((item) => !item.adminOnly || isAdmin),
        }))
        .filter((section) => section.items.length > 0),
    [isAdmin],
  );

  return (
    <nav aria-label="主导航">
      <Listbox aria-label="主导航" selectedKeys={new Set([route])} selectionMode="single" variant="flat" onAction={(key) => setRoute(String(key) as RouteKey)}>
        {sections.map((section) => (
          <ListboxSection key={section.title} title={section.title} classNames={{ heading: "px-2 text-[11px] font-semibold uppercase tracking-wide text-default-400" }}>
            {section.items.map((item) => {
              const Icon = item.icon;
              return (
                <ListboxItem key={item.key} startContent={<Icon size={16} aria-hidden="true" />} onPress={() => setRoute(item.key)}>
                  {item.label}
                </ListboxItem>
              );
            })}
          </ListboxSection>
        ))}
      </Listbox>
    </nav>
  );
}

function UserMenu({ fullWidth = false }: { fullWidth?: boolean }) {
  const { user, membership, logout } = useAuthStore();

  return (
    <Dropdown placement="bottom-end">
      <DropdownTrigger>
        <Button
          variant="light"
          className={fullWidth ? "w-full justify-start px-2" : "px-2"}
          startContent={<Avatar name={user?.username?.slice(0, 1).toUpperCase()} size="sm" />}
        >
          <span className="hidden max-w-28 truncate sm:inline">{user?.username}</span>
        </Button>
      </DropdownTrigger>
      <DropdownMenu aria-label="用户菜单" onAction={(key) => key === "logout" && logout()}>
        <DropdownItem key="role" isReadOnly textValue="当前角色">
          <div className="flex items-center justify-between gap-8 text-sm">
            <span className="text-default-500">当前角色</span>
            {membership ? <Chip size="sm">{roleLabel[membership.role]}</Chip> : <Chip size="sm">无团队</Chip>}
          </div>
        </DropdownItem>
        <DropdownItem key="logout" color="danger" startContent={<LogOut size={16} aria-hidden="true" />}>
          退出登录
        </DropdownItem>
      </DropdownMenu>
    </Dropdown>
  );
}
