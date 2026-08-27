import { Button, Card, CardBody, Input, Select, SelectItem, Skeleton, Table, TableBody, TableCell, TableColumn, TableHeader, TableRow } from "@heroui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { addMember, listMembers, removeMember, updateMemberRole, type Role } from "../api/m1";
import { firstKey } from "../app/navigation";
import { PageHeader } from "../components/PageHeader";

export function MembersPage() {
  const queryClient = useQueryClient();
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<Role>("viewer");
  const { data = [], isLoading } = useQuery({ queryKey: ["members"], queryFn: listMembers });
  const addMutation = useMutation({
    mutationFn: () => addMember({ username, role }),
    onSuccess: () => {
      setUsername("");
      queryClient.invalidateQueries({ queryKey: ["members"] });
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ userId, nextRole }: { userId: string; nextRole: Role }) => updateMemberRole(userId, nextRole),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["members"] }),
  });
  const removeMutation = useMutation({ mutationFn: removeMember, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["members"] }) });

  return (
    <section className="space-y-5">
      <PageHeader title="团队成员" description="添加已注册用户并分配团队角色。" />
      <Card shadow="sm">
        <CardBody>
          <form
            className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              addMutation.mutate();
            }}
          >
            <Input label="用户名" value={username} onValueChange={setUsername} />
            <Select label="角色" selectedKeys={new Set([role])} onSelectionChange={(keys) => setRole(firstKey(keys, "viewer") as Role)}>
              <SelectItem key="admin">管理员</SelectItem>
              <SelectItem key="editor">编辑者</SelectItem>
              <SelectItem key="viewer">查看者</SelectItem>
            </Select>
            <Button className="self-end" color="primary" type="submit" isLoading={addMutation.isPending}>
              添加成员
            </Button>
          </form>
        </CardBody>
      </Card>
      <Table aria-label="团队成员列表" shadow="sm">
        <TableHeader>
          <TableColumn>用户</TableColumn>
          <TableColumn>角色</TableColumn>
          <TableColumn>加入时间</TableColumn>
          <TableColumn>操作</TableColumn>
        </TableHeader>
        <TableBody emptyContent="暂无成员">
          {isLoading
            ? Array.from({ length: 4 }).map((_, index) => (
                <TableRow key={`member-loading-${index}`} aria-label="成员加载中">
                  <TableCell>
                    <Skeleton className="h-4 w-28 rounded-md" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-8 w-36 rounded-lg" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-4 w-40 rounded-md" />
                  </TableCell>
                  <TableCell>
                    <Skeleton className="h-8 w-16 rounded-lg" />
                  </TableCell>
                </TableRow>
              ))
            : data.map((member) => (
                <TableRow key={member.id}>
                  <TableCell>{member.user.username}</TableCell>
                  <TableCell>
                    <Select
                      aria-label={`${member.user.username} 的角色`}
                      size="sm"
                      className="w-36"
                      selectedKeys={new Set([member.role])}
                      onSelectionChange={(keys) => updateMutation.mutate({ userId: member.user.id, nextRole: firstKey(keys, member.role) as Role })}
                    >
                      <SelectItem key="admin">管理员</SelectItem>
                      <SelectItem key="editor">编辑者</SelectItem>
                      <SelectItem key="viewer">查看者</SelectItem>
                    </Select>
                  </TableCell>
                  <TableCell>{new Date(member.created_at).toLocaleString()}</TableCell>
                  <TableCell>
                    <Button size="sm" color="danger" variant="flat" onPress={() => removeMutation.mutate(member.user.id)}>
                      移除
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
        </TableBody>
      </Table>
    </section>
  );
}
