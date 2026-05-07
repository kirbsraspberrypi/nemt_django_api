SELECT
    TO_CHAR(re_pickup.created_at AT TIME ZONE 'UTC', 'YYYY-MM') AS month,
    u.first_name || ' ' || LEFT(u.last_name, 1)                 AS driver,
    COUNT(*)                                                      AS count_of_trips_gt_1hr
FROM ride r
JOIN "user" u
    ON u.id_user = r.id_driver
JOIN ride_event re_pickup
    ON  re_pickup.id_ride     = r.id_ride
    AND re_pickup.description = 'Status changed to pickup'
JOIN ride_event re_dropoff
    ON  re_dropoff.id_ride     = r.id_ride
    AND re_dropoff.description = 'Status changed to dropoff'
WHERE
    re_dropoff.created_at - re_pickup.created_at > INTERVAL '1 hour'
GROUP BY
    TO_CHAR(re_pickup.created_at AT TIME ZONE 'UTC', 'YYYY-MM'),
    u.id_user,
    u.first_name,
    u.last_name
ORDER BY
    month  ASC,
    driver ASC;
