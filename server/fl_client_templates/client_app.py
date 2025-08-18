"""Flower ClientApp template (PyTorch)."""

import torch
from flwr.client import ClientApp, NumPyClient
from flwr.common import Context


class SimpleClient(NumPyClient):
    def __init__(self, device: torch.device, input_size: int, hidden: int, output_size: int, local_epochs: int):
        self.device = device
        self.input_size = input_size
        self.hidden = hidden
        self.output_size = output_size
        self.local_epochs = local_epochs
        self.model = torch.nn.Sequential(
            torch.nn.Linear(input_size, hidden),
            torch.nn.ReLU(),
            torch.nn.Linear(hidden, output_size),
        ).to(self.device)
        self.criterion = torch.nn.CrossEntropyLoss()
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)

    def fit(self, parameters, config):
        # Ignore parameters for simplicity (startup from random)
        steps = int(config.get("steps", 50))
        for _ in range(self.local_epochs):
            for _ in range(steps):
                x = torch.randn(32, self.input_size, device=self.device)
                y = torch.randint(0, self.output_size, (32,), device=self.device)
                self.optimizer.zero_grad(set_to_none=True)
                loss = self.criterion(self.model(x), y)
                loss.backward()
                self.optimizer.step()
        return [], 32 * steps, {"train_loss": float(loss.item())}

    def evaluate(self, parameters, config):
        with torch.no_grad():
            x = torch.randn(128, self.input_size, device=self.device)
            y = torch.randint(0, self.output_size, (128,), device=self.device)
            loss = self.criterion(self.model(x), y).item()
            acc = float((self.model(x).argmax(dim=1) == y).float().mean().item())
        return float(loss), 128, {"accuracy": acc}


def client_fn(context: Context):
    # Device selection
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Read from run_config
    cfg = context.run_config
    input_size = int(cfg.get("input-size", 128))
    hidden = int(cfg.get("hidden", 64))
    output_size = int(cfg.get("output-size", 10))
    local_epochs = int(cfg.get("local-epochs", 1))

    return SimpleClient(device, input_size, hidden, output_size, local_epochs).to_client()


app = ClientApp(client_fn)
