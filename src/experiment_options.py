"""The fixed vocabulary of the experiment, shared by training, the database and the assistant.

The database CHECK constraints (sql/migrations) list the same values. Change both together.
"""

ALGORITHMS = ("A2C", "DQN", "PPO")
FEATURE_SETS = ("standard", "indicators")

# "test": the held-out window TEST_START..TEST_END.
# "forward": every trading day after TEST_END, added by `make refresh` ("performance since training").
EVALUATION_PERIODS = ("test", "forward")
