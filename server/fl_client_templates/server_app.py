# server_app.py
import flwr as fl
app = fl.server.ServerApp()

# remote-federation에선 이 함수가 호출되지 않습니다.
@app.server_fn
def server_fn(ctx: fl.common.Context):
    # 호출되지 않지만, 형식만 맞춰 둡니다.
    return fl.server.ServerAppComponents(
        strategy=fl.server.strategy.FedAvg(),
        config=fl.server.ServerConfig(num_rounds=1),
    )