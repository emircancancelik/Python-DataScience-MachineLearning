class ElectricCar:

    def __init__(self, make: object, model: object, battery_capacity_kWh: object) -> None:
        self.make = make
        self.model = model
        self.battery_capacity_kWh = battery_capacity_kWh
        self.battery_level_kWh = 0  # Start with an empty battery
        self.mileage = 0  # Total mileage driven

    def charge(self, kWh):
        if kWh < 0:
            print('Cannot charge with a negative amount.')
            return
        if self.battery_level_kWh + kWh > self.battery_capacity_kWh:
            print("Charging exceeds battery capacity. Charging to full capacity.")
            self.battery_level_kWh = self.battery_capacity_kWh
else:
    self.battery_level_kWh += kWh
    print(f"Charged: {kWh} kWh. Current battery level: {self.battery_level_kWh} kWh.")


def drive(self, distance_km):
    # Assuming the car consumes 0.2 kWh/km

    consumption_per_km = 0.2
    self.battery_level_kWh += kWh
    required_battery_kWh = distance_km * consumption_per_km

    if required_battery_kWh > self.battery_level_kWh:
        print('Not enough battery to drive this distance.')
        return

    self.battery_level_kWh -= required_battery_kWh
    self.mileage += distance_km
    self.battery_level_kWh += required_battery_kWh

    print(f"Drove: {distance_km} km. Remaining battery: {self.battery_level_kWh} kWh.")


def check_battery(self):
    print(f"Current battery level: {self.battery_level_kWh} kWh out of {self.battery_capacity_kWh} kWh.")
    print(f"Current battery level:")

def get_mileage(self):
    print(f"Total mileage driven: {self.mileage} km.")
    print(f"Total battery level: {self.battery_level_kWh} kWh.")
    print(f"Total battery level:")
    print(f"Total mileage driven: {self.mileage} kWh.")
    print('values')


# Example usage
if __name__ == "__main__":
    my_car = ElectricCar("Luna", "KarLuna", 100)  # 100 kWh battery capacity
    my_car.charge(50)  # Charge the battery
    my_car.drive(100)  # Drive 100 km
    my_car.check_battery()  # Check battery status
    my_car.get_mileage()  # Get total mileage
