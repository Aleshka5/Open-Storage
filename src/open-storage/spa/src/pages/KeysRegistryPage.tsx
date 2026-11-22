import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Copy, Plus, Trash2 } from "lucide-react";
import { PageFrame } from "../components/Layout/PageFrame";
import { PrivateUnlockModal } from "../components/PrivateUnlockModal";
import { Button } from "../components/ui/Button";
import { ErrorMessage } from "../components/ui/ErrorMessage";
import { Input } from "../components/ui/Input";
import { LoadingBlock } from "../components/ui/LoadingBlock";
import { Modal } from "../components/ui/Modal";
import { usePrivateSession } from "../hooks/usePrivateSession";
import { getApiErrorDetail } from "../services/api";
import { listKeys, saveKeys, type RegistryKey } from "../services/keysApi";
import { showErrorToast, showSuccessToast } from "../utils/toast";

function maskKeyValue(value: string): string {
  if (value.length <= 8) {
    return "••••";
  }
  return `${value.slice(0, 4)}...${value.slice(-4)}`;
}

const ADD_ERROR_MESSAGES: Record<string, string> = {
  KEY_NAME_EMPTY: "Key name cannot be empty",
  KEY_VALUE_EMPTY: "Key value cannot be empty",
  KEY_NAME_DUPLICATE: "A key with this name already exists",
};

export default function KeysRegistryPage() {
  const navigate = useNavigate();
  const { isActive, isLoading, showUnlockModal, onUnlockSuccess } = usePrivateSession();
  const [keys, setKeys] = useState<RegistryKey[]>([]);
  const [isFetching, setIsFetching] = useState(false);
  const [isDeletingKey, setIsDeletingKey] = useState(false);
  const [loadError, setLoadError] = useState<string | undefined>();
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newValue, setNewValue] = useState("");
  const [addError, setAddError] = useState<string | undefined>();
  const [addNotice, setAddNotice] = useState<string | undefined>();
  const [isAdding, setIsAdding] = useState(false);
  const [keyToDelete, setKeyToDelete] = useState<string | null>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);

  const loadRegistry = useCallback(async () => {
    setIsFetching(true);
    setLoadError(undefined);

    try {
      const data = await listKeys();
      setKeys(data.keys);
    } catch (error) {
      const detail = getApiErrorDetail(error);
      if (detail?.error_code === "PRIVATE_SESSION_EXPIRED") {
        return;
      }
      setLoadError(detail?.error_code ?? "INTERNAL_ERROR");
      showErrorToast(error);
    } finally {
      setIsFetching(false);
    }
  }, []);

  useEffect(() => {
    if (!isActive) {
      return;
    }
    void loadRegistry();
  }, [isActive, loadRegistry]);

  useEffect(() => {
    if (isAddOpen) {
      nameInputRef.current?.focus();
    }
  }, [isAddOpen]);

  const handleCancelUnlock = useCallback(() => {
    navigate("/files");
  }, [navigate]);

  const handleUnlockSuccess = useCallback(() => {
    onUnlockSuccess();
  }, [onUnlockSuccess]);

  const handleCopy = useCallback(async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      showSuccessToast("Copied to clipboard");
    } catch {
      showErrorToast(new Error("Could not copy to clipboard"));
    }
  }, []);

  const closeAddModal = useCallback(() => {
    setIsAddOpen(false);
    setNewName("");
    setNewValue("");
    setAddError(undefined);
    setAddNotice(undefined);
  }, []);

  const handleAdd = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const name = newName.trim();
      const value = newValue.trim();

      if (!name) {
        setAddError("Key name cannot be empty");
        return;
      }
      if (!value) {
        setAddError("Key value cannot be empty");
        return;
      }
      if (keys.some((key) => key.name === name)) {
        setAddError("A key with this name already exists");
        return;
      }

      setIsAdding(true);
      setAddError(undefined);
      setAddNotice(undefined);

      try {
        const data = await saveKeys([...keys, { name, value }]);
        setKeys(data.keys);
        setNewName("");
        setNewValue("");
        setAddNotice(`Saved “${name}”. Add the next key or close this dialog.`);
        nameInputRef.current?.focus();
      } catch (error) {
        const detail = getApiErrorDetail(error);
        if (detail?.error_code === "PRIVATE_SESSION_EXPIRED") {
          closeAddModal();
          return;
        }
        const inlineMessage = detail?.error_code
          ? ADD_ERROR_MESSAGES[detail.error_code]
          : undefined;
        if (inlineMessage) {
          setAddError(inlineMessage);
        } else {
          setAddError(detail?.message ?? "Could not save the key. Try again.");
          showErrorToast(error);
        }
      } finally {
        setIsAdding(false);
      }
    },
    [closeAddModal, keys, newName, newValue],
  );

  const confirmDelete = useCallback(async () => {
    if (keyToDelete === null) {
      return;
    }

    setIsDeletingKey(true);

    try {
      const data = await saveKeys(keys.filter((key) => key.name !== keyToDelete));
      setKeys(data.keys);
      showSuccessToast(`Deleted “${keyToDelete}”`);
      setKeyToDelete(null);
    } catch (error) {
      const detail = getApiErrorDetail(error);
      if (detail?.error_code === "PRIVATE_SESSION_EXPIRED") {
        setKeyToDelete(null);
        return;
      }
      showErrorToast(error);
    } finally {
      setIsDeletingKey(false);
    }
  }, [keyToDelete, keys]);

  if (isLoading) {
    return (
      <PageFrame title="Keys" lead="Names and secrets kept with the private passphrase.">
        <LoadingBlock active label="Loading keys…" />
      </PageFrame>
    );
  }

  return (
    <PageFrame
      title="Keys"
      lead="Names and secrets kept with the private passphrase. Every change is saved immediately."
      actions={
        isActive ? (
          <div className="actions">
            <Button type="button" variant="secondary" onClick={() => setIsAddOpen(true)}>
              <Plus size={16} aria-hidden="true" />
              Add key
            </Button>
          </div>
        ) : undefined
      }
    >
      {isActive && (
        <div>
          {isFetching ? (
            <LoadingBlock active label="Loading keys…" />
          ) : loadError ? (
            <div className="error-block">
              <ErrorMessage errorCode={loadError} />
              <Button type="button" onClick={() => void loadRegistry()}>
                Reload
              </Button>
            </div>
          ) : keys.length === 0 ? (
            <div className="empty">
              <p>No keys yet.</p>
              <Button type="button" variant="secondary" onClick={() => setIsAddOpen(true)}>
                <Plus size={16} aria-hidden="true" />
                Add key
              </Button>
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Key name</th>
                    <th>Value</th>
                    <th>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {keys.map((key) => (
                    <tr key={key.name}>
                      <td>{key.name}</td>
                      <td className="meta-code">{maskKeyValue(key.value)}</td>
                      <td>
                        <div className="cell-actions">
                          <button
                            type="button"
                            title="Copy value"
                            aria-label={`Copy ${key.name}`}
                            className="icon-btn"
                            onClick={() => {
                              void handleCopy(key.value);
                            }}
                          >
                            <Copy size={16} />
                          </button>
                          <button
                            type="button"
                            title="Delete key"
                            aria-label={`Delete ${key.name}`}
                            className="icon-btn danger"
                            disabled={isDeletingKey}
                            onClick={() => setKeyToDelete(key.name)}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <PrivateUnlockModal
        isOpen={showUnlockModal}
        onSuccess={handleUnlockSuccess}
        onCancel={handleCancelUnlock}
      />

      <Modal isOpen={isAddOpen} onClose={closeAddModal} title="Add key">
        <form className="stack" onSubmit={handleAdd}>
          <Input
            label="Key name"
            ref={nameInputRef}
            value={newName}
            onChange={(event) => {
              setNewName(event.target.value);
              setAddError(undefined);
              setAddNotice(undefined);
            }}
            autoComplete="off"
            disabled={isAdding}
          />
          <Input
            label="Value"
            type="password"
            value={newValue}
            onChange={(event) => {
              setNewValue(event.target.value);
              setAddError(undefined);
              setAddNotice(undefined);
            }}
            autoComplete="off"
            disabled={isAdding}
          />
          {addError && <p className="form-error">{addError}</p>}
          {addNotice && <p className="form-note">{addNotice}</p>}
          <div className="actions">
            <Button type="button" variant="secondary" onClick={closeAddModal} disabled={isAdding}>
              Close
            </Button>
            <Button type="submit" isLoading={isAdding}>
              Add
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={keyToDelete !== null}
        onClose={() => {
          if (!isDeletingKey) {
            setKeyToDelete(null);
          }
        }}
        title="Delete key?"
      >
        {keyToDelete !== null && (
          <>
            <p>
              Key “{keyToDelete}” will be removed from the registry immediately. This cannot be
              undone.
            </p>
            <div className="actions">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setKeyToDelete(null)}
                disabled={isDeletingKey}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                isLoading={isDeletingKey}
                onClick={() => {
                  void confirmDelete();
                }}
              >
                Delete
              </Button>
            </div>
          </>
        )}
      </Modal>
    </PageFrame>
  );
}
